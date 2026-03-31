#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图表操作：创建、更新、查询、详情、可视化配置。"""

from __future__ import annotations

import argparse, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from _api import (
    CHART_SUB_TYPES, DATASOURCE_TYPES, DEFAULT_MAX_ROWS, TaskExpiredError,
    api_batch_get, api_delete, api_get, api_post, api_put,
    extract_creator, extract_id, extract_sql_variables, extract_task_id,
    parse_json_arg, parse_tags, poll_async_task, poll_async_tasks_batch,
    poll_chart_task, print_error, print_result, resolve_datasource,
)


def _resolve_sql(args) -> str:
    """从 CLI 参数中解析 SQL（--sql 或 --sql-file）。"""
    sql = args.sql
    if getattr(args, "sql_file", None):
        with open(args.sql_file, "r", encoding="utf-8") as f:
            sql = f.read()
    return sql


def _submit_async_query(chart_id: str, body: dict, dashboard_id: str, use_cache: bool) -> str:
    """提交异步图表查询，返回 task ID。"""
    if dashboard_id:
        result = api_post(f"/dashboard-query/charts/async/{chart_id}", body=body,
                          params={"dashboardId": dashboard_id, "isCache": use_cache})
    else:
        result = api_post(f"/charts/query/async/{chart_id}", body=body)
    return extract_task_id(result.get("data", result))


def create_chart(name: str, sql: str, datasource_type="TRINO", catalog="hive",
                 tags=None, description="", arguments=None) -> dict:
    """创建 SQL 图表（含 SQL 保存和参数依赖）。"""
    ds = resolve_datasource(datasource_type)
    if ds not in DATASOURCE_TYPES:
        raise ValueError(f"不支持的数据源: {datasource_type}，支持: {', '.join(DATASOURCE_TYPES)}")

    sql_vars = extract_sql_variables(sql)

    if arguments is None:
        arguments = _infer_arguments(sql_vars)

    body = {"name": name, "type": "SQL"}
    if tags: body["customTags"] = tags
    if description: body["description"] = description

    result = api_post("/charts", body=body)
    chart_id = extract_id(result.get("data", ""))
    if not chart_id:
        raise RuntimeError("图表创建失败，API 未返回 ID")

    sql_body = {"id": chart_id, "type": "SQL", "sql": sql, "dataSourceType": ds, "catalog": catalog}
    if arguments: sql_body["arguments"] = arguments

    warnings, sql_saved = {}, False
    try:
        api_put(f"/sql-lab/{chart_id}", body=sql_body)
        sql_saved = True
    except Exception as e:
        warnings["sqlLab"] = str(e)

    info = {"chartId": chart_id, "name": name, "dataSourceType": ds,
            "sqlVariables": sql_vars, "sqlSaved": sql_saved, "message": f"图表 '{name}' 创建成功！"}
    if warnings: info["warnings"] = warnings
    return info


def _infer_arguments(sql_vars: list) -> list:
    """根据 SQL 变量名自动推断参数定义。
    - xxx.start / xxx.end → DATE_RANGE 或 TIME 范围
    - xxx.min / xxx.max → NUMBER_RANGE
    - 关键词匹配推断 DATE_RANGE / NUMBER / LIST
    """
    _DATE_KW = ("date", "dt", "日期")
    _TIME_KW = ("time", "datetime", "timestamp", "时间")
    _NUM_KW = ("num", "count", "amount", "qty", "limit", "threshold", "数量", "金额")

    today = date.today()
    default_date_range = [(today - timedelta(days=7)).isoformat(), today.isoformat()]

    range_bases = {}  # base_name -> {"suffix_type": "date"|"time"|"number"}
    plain_vars = []
    for var in sql_vars:
        matched = False
        for suffix, stype in ((".start", None), (".end", None), (".min", "number"), (".max", "number")):
            if var.endswith(suffix):
                base = var[: -len(suffix)]
                if base not in range_bases:
                    bl = base.lower().replace(" ", "")
                    if stype == "number":
                        range_bases[base] = "number"
                    elif any(k in bl for k in _TIME_KW):
                        range_bases[base] = "time"
                    else:
                        range_bases[base] = "date"
                matched = True
                break
        if not matched:
            plain_vars.append(var)

    seen, arguments = set(), []
    for base, rtype in range_bases.items():
        if base in seen:
            continue
        seen.add(base)
        if rtype == "number":
            arguments.append({"source": "CUSTOM", "keyword": base, "title": base,
                              "type": "NUMBER_RANGE", "quotation": "NONE"})
        elif rtype == "time":
            arguments.append({"source": "CUSTOM", "keyword": base, "title": base,
                              "type": "TIME_MINUTE_RANGE", "quotation": "NONE"})
        else:
            arguments.append({"source": "CUSTOM", "keyword": base, "title": base,
                              "type": "DATE_RANGE", "quotation": "NONE",
                              "defaultValues": default_date_range})
    for var in plain_vars:
        if var in seen:
            continue
        seen.add(var)
        vl = var.lower().replace(" ", "")
        if any(k in vl for k in _TIME_KW):
            arguments.append({"source": "CUSTOM", "keyword": var, "title": var,
                              "type": "TIME_MINUTE_RANGE", "quotation": "NONE"})
        elif any(k in vl for k in _DATE_KW):
            arguments.append({"source": "CUSTOM", "keyword": var, "title": var,
                              "type": "DATE_RANGE", "quotation": "NONE",
                              "defaultValues": default_date_range})
        elif any(k in vl for k in _NUM_KW):
            arguments.append({"source": "CUSTOM", "keyword": var, "title": var,
                              "type": "NUMBER", "quotation": "NONE"})
        else:
            arguments.append({"source": "CUSTOM", "keyword": var, "title": var,
                              "type": "LIST", "multipleValue": True, "quotation": "SINGLE"})
    return arguments


def create_visualization(chart_id: str, viz_type: str, viz_name="",
                         options=None, from_dashboard_id="") -> dict:
    """创建或更新可视化配置。已有同类型 viz 则 PUT 更新，否则 POST 创建。"""
    body = {}
    vt = viz_type.upper()
    if vt in CHART_SUB_TYPES:
        body["type"] = "CHART"
        body["options"] = dict(options or {})
        body["options"]["type"] = vt.lower()
    else:
        body["type"] = vt
        if options: body["options"] = options
    if viz_name: body["name"] = viz_name
    if from_dashboard_id: body["fromDashboardId"] = from_dashboard_id

    # 查已有 viz，有则更新，无则创建
    detail = api_get(f"/charts/detail/{chart_id}").get("data", {})
    existing_vizs = detail.get("visualizations") or []

    target_viz = None
    for v in reversed(existing_vizs):
        if v.get("type") == body.get("type") and v.get("id"):
            target_viz = v
            break

    if target_viz:
        merged_opts = dict(target_viz.get("options") or {})
        merged_opts.update(body.get("options", {}))
        body["options"] = merged_opts
        api_put(f"/charts/visualization/{target_viz['id']}", body=body)
        viz_id = target_viz["id"]
        action = "更新"
    else:
        result = api_post(f"/charts/charts/{chart_id}/visualization", body=body)
        viz_id = extract_id(result.get("data", ""))
        action = "创建"

    info = {"chartId": chart_id, "visualizationId": viz_id, "type": vt,
            "message": f"可视化配置{action}成功！"}

    # 创建新 viz 时自动回写 dashboard widget 的 visualizationId
    if action == "创建" and from_dashboard_id and viz_id:
        try:
            raw = api_get(f"/dashboard-mgr/{from_dashboard_id}").get("data", {})
            widgets = raw.get("widgets") or []
            updated_count = 0
            for w in widgets:
                if w.get("chartsId") == chart_id:
                    w["visualizationId"] = viz_id
                    if w.get("visualization"):
                        w["visualization"]["id"] = viz_id
                    updated_count += 1
            if updated_count > 0:
                api_put(f"/dashboard-mgr/{from_dashboard_id}", body={
                    "id": from_dashboard_id,
                    "name": raw.get("name"),
                    "description": raw.get("description"),
                    "customTags": raw.get("customTags"),
                    "parameters": raw.get("parameters"),
                    "options": raw.get("options"),
                    "widgets": widgets,
                })
                info["dashboardUpdated"] = True
                info["widgetsUpdated"] = updated_count
        except Exception as e:
            info["dashboardUpdateError"] = str(e)

    return info


def update_chart(chart_id: str, name=None, sql=None, datasource_type=None,
                 catalog=None, tags=None, arguments=None) -> dict:
    """更新图表的名称、标签、SQL、数据源或参数。"""
    updated = []

    chart_body = {}
    if name is not None: chart_body["name"] = name
    if tags is not None: chart_body["customTags"] = tags
    if chart_body:
        api_put(f"/charts/{chart_id}", body=chart_body)
        updated.extend(chart_body.keys())

    if any(v is not None for v in (sql, datasource_type, catalog, arguments)):
        sb = {"id": chart_id, "type": "SQL"}
        if sql is not None: sb["sql"] = sql; updated.append("sql")
        if datasource_type is not None: sb["dataSourceType"] = resolve_datasource(datasource_type); updated.append("dataSourceType")
        if catalog is not None: sb["catalog"] = catalog; updated.append("catalog")

        # 需要从已有详情补全 dataSourceType 或合并 arguments 时，只请求一次
        existing = None
        if "dataSourceType" not in sb or (arguments is None and sql is not None):
            try:
                existing = api_get(f"/charts/detail/{chart_id}").get("data", {})
            except Exception:
                existing = {}

        if "dataSourceType" not in sb:
            sb["dataSourceType"] = (existing or {}).get("dataSourceType", "TRINO")

        if arguments is not None:
            sb["arguments"] = arguments; updated.append("arguments")
        elif sql is not None:
            existing_args = {a["keyword"]: a for a in (existing or {}).get("arguments", []) if a.get("keyword")}
            inferred = {a["keyword"]: a for a in _infer_arguments(extract_sql_variables(sql))}
            merged = []
            for kw in inferred:
                merged.append(existing_args[kw] if kw in existing_args else inferred[kw])
            sb["arguments"] = merged
        api_put(f"/sql-lab/{chart_id}", body=sb)

    if not updated:
        raise ValueError("至少需要提供一个要更新的字段")

    info = {"chartId": chart_id, "message": "图表更新成功！", "updatedFields": updated}
    return info


def get_chart_detail(chart_id: str, from_dashboard_id="") -> dict:
    """获取图表完整详情。"""
    params = {"fromDashboardId": from_dashboard_id} if from_dashboard_id else {}
    result = api_get(f"/charts/detail/{chart_id}", params=params)
    data = result.get("data", result)

    info = {k: data.get(k, "") for k in ("id", "name", "description", "catalog", "dataSourceType",
                                           "type", "sql", "createdAt", "updatedAt")}
    info["id"] = info["id"] or chart_id
    info["customTags"] = data.get("customTags")
    info["permission"] = data.get("permission", 0)

    if info.get("sql"):
        info["sqlVariables"] = extract_sql_variables(info["sql"])

    info["arguments"] = data.get("arguments", [])
    info["argumentDependencies"] = data.get("argumentDependencies", [])

    slim_viz = []
    for v in data.get("visualizations", []):
        sv = {"id": v.get("id", ""), "name": v.get("name", ""), "type": v.get("type", "")}
        opts = v.get("options") or {}
        sv["options"] = {k: opts[k] for k in (
                         "type", "xAxis", "yAxises", "group", "stack", "showLegend", "showLabel",
                         "showSymbol", "showAsPercent", "treatMissing",
                         "xAxisOption", "yAxisOption", "yAxisRight", "seriesOptions",
                         "tooltip", "direction",
                         "countColumn", "targetColumn", "decimalPlaces", "prefix", "suffix",
                         "xColumn", "yColumn", "colorColumn", "nameColumn", "valueColumn",
                         "pageSize",
                         ) if k in opts}
        slim_viz.append(sv)
    info["visualizations"] = slim_viz

    info.update(extract_creator(data))
    return info


def build_arguments(args_dict: dict) -> list:
    return [{"keyword": k, "values": v if isinstance(v, list) else [str(v)]}
            for k, v in args_dict.items()]


def _build_dashboard_arguments(dashboard_id: str) -> list:
    """从 Dashboard 的 paramConfigs + parameters.defaultValues + 图表 arguments.defaultValues 自动构建查询参数。
    优先级：paramConfigs（用户当前筛选值）> parameters.defaultValues > 图表 arguments.defaultValues。"""
    raw = api_get(f"/dashboard-mgr/{dashboard_id}").get("data", {})

    pc_map = {}
    for pc in (raw.get("paramConfigs") or []):
        key = pc.get("key", "")
        vals = pc.get("values") or []
        if key and vals:
            pc_map[key] = vals

    for p in (raw.get("parameters") or []):
        key = p.get("key", "")
        if key and key not in pc_map:
            defaults = p.get("defaultValues") or []
            if defaults:
                pc_map[key] = defaults

    # 遍历图表级 arguments.defaultValues 补齐独有参数（如仅部分图表使用的参数）
    chart_ids = list({w.get("chartsId") for w in (raw.get("widgets") or []) if w.get("chartsId")})
    if chart_ids:
        chart_results = api_batch_get([f"/charts/detail/{cid}" for cid in chart_ids])
        for res in chart_results:
            cd = res.get("data", res)
            if not isinstance(cd, dict):
                continue
            for arg in (cd.get("arguments") or []):
                kw = arg.get("keyword", "")
                if kw and kw not in pc_map:
                    defaults = arg.get("defaultValues") or []
                    if defaults:
                        pc_map[kw] = defaults

    return [{"keyword": k, "values": v} for k, v in pc_map.items()]


def query_chart(chart_id: str, dashboard_id="", arguments=None,
                use_async=False, use_cache=True, max_rows=DEFAULT_MAX_ROWS) -> dict:
    """执行单个图表查询。传了 dashboard_id 时走 dashboard 查询路径（同步优先，--async 时走异步）。"""
    body = {"arguments": arguments or []}

    for _attempt in range(3):
        try:
            if dashboard_id:
                if use_async:
                    tid = _submit_async_query(chart_id, body, dashboard_id, use_cache)
                    if tid:
                        return _fmt_result(poll_async_task(tid), max_rows)
                    return _fmt_result({}, max_rows)
                else:
                    data = api_post(f"/dashboard-query/charts/{chart_id}", body=body,
                                    params={"dashboardId": dashboard_id, "isCache": use_cache}).get("data", {})
                    return _fmt_result(data, max_rows)
            elif use_async:
                tid = _submit_async_query(chart_id, body, "", use_cache)
                if tid:
                    return _fmt_result(poll_chart_task(tid), max_rows)
                return _fmt_result({}, max_rows)
            else:
                data = api_post(f"/charts/query/{chart_id}", body=body).get("data", {})
                return _fmt_result(data, max_rows)
        except TaskExpiredError:
            use_cache = False
            continue
    raise RuntimeError(f"图表 {chart_id} 查询任务反复过期，已重试 2 次")


def query_charts_batch(chart_ids, dashboard_id="", arguments=None,
                       use_cache=True, max_rows=DEFAULT_MAX_ROWS, max_workers=6) -> dict:
    """并发查询多个图表（异步提交 + 并发轮询）。"""
    # 按图表过滤参数 + 预检参数完整性
    arg_by_chart = {}
    skipped = {}
    if arguments and dashboard_id:
        chart_results = api_batch_get([f"/charts/detail/{cid}" for cid in chart_ids])
        for cid, res in zip(chart_ids, chart_results):
            cd = res.get("data", res)
            if not isinstance(cd, dict):
                arg_by_chart[cid] = arguments
                continue
            chart_args_def = cd.get("arguments") or []
            all_keys = {a.get("keyword") for a in chart_args_def if a.get("keyword")}
            provided_keys = {a.get("keyword") for a in arguments if a.get("keyword")}
            # 找出缺失且无默认值的必需参数
            missing = [a.get("keyword") for a in chart_args_def
                       if a.get("keyword") and a["keyword"] not in provided_keys
                       and not a.get("defaultValues")]
            if missing:
                skipped[cid] = {"skipped": True,
                                "reason": f"缺少必需参数: {', '.join(missing)}",
                                "missingParams": missing}
            else:
                # 过滤用户提供的参数 + 用 defaultValues 补齐用户未传但有默认值的参数
                filtered = [a for a in arguments if a.get("keyword") in all_keys]
                filled_keys = {a.get("keyword") for a in filtered}
                for a in chart_args_def:
                    kw = a.get("keyword", "")
                    if kw and kw not in filled_keys and a.get("defaultValues"):
                        filtered.append({"keyword": kw, "values": a["defaultValues"]})
                arg_by_chart[cid] = filtered

    submit_ids = [cid for cid in chart_ids if cid not in skipped]
    task_map, errors = {}, {}

    def _submit(cid):
        try:
            chart_args = arg_by_chart.get(cid, arguments or [])
            body = {"arguments": chart_args}
            tid = _submit_async_query(cid, body, dashboard_id, use_cache)
            return cid, tid, None
        except Exception as e:
            return cid, "", str(e)

    if submit_ids:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(submit_ids))) as pool:
            for f in as_completed([pool.submit(_submit, c) for c in submit_ids]):
                cid, tid, err = f.result()
                if tid: task_map[tid] = cid
                else: errors[cid] = err or "未知错误"

    # 全部提交失败或跳过时直接返回
    if not task_map:
        results = dict(skipped)
        results.update({cid: {"error": f"提交失败: {err}"} for cid, err in errors.items()})
        return results

    poll_fn = poll_async_task if dashboard_id else poll_chart_task
    task_results = poll_async_tasks_batch(list(task_map.keys()), max_workers=max_workers, poll_fn=poll_fn)

    results = dict(skipped)
    expired_cids = []
    for tid, td in task_results.items():
        cid = task_map.get(tid, tid)
        if isinstance(td, dict) and td.get("expired"):
            expired_cids.append(cid)
        elif isinstance(td, dict) and "error" in td:
            results[cid] = {"error": td["error"]}
        else:
            results[cid] = _fmt_result(td, max_rows)

    # 过期任务重试：强制 use_cache=False 重新提交
    if expired_cids:
        retry_map = {}
        for cid in expired_cids:
            try:
                chart_args = arg_by_chart.get(cid, arguments or [])
                tid = _submit_async_query(cid, {"arguments": chart_args}, dashboard_id, use_cache=False)
                if tid:
                    retry_map[tid] = cid
                else:
                    results[cid] = {"error": "重试提交失败: 未返回 task ID"}
            except Exception as e:
                results[cid] = {"error": f"重试提交失败: {e}"}
        if retry_map:
            retry_results = poll_async_tasks_batch(
                list(retry_map.keys()), max_workers=max_workers, poll_fn=poll_fn)
            for tid, td in retry_results.items():
                cid = retry_map[tid]
                results[cid] = {"error": td["error"]} if isinstance(td, dict) and "error" in td else _fmt_result(td, max_rows)

    for cid, err in errors.items():
        if cid not in results:
            results[cid] = {"error": f"提交失败: {err}"}
    return results


def example_query(chart_id: str, datasource_type: str, arguments=None,
                  max_rows=DEFAULT_MAX_ROWS) -> dict:
    """通过 example/query 接口执行图表查询，支持临时覆盖数据源。"""
    detail = api_get(f"/charts/detail/{chart_id}").get("data", {})
    if not detail.get("sql"):
        raise ValueError(f"图表 {chart_id} 没有 SQL")

    # 构建 values：从 arguments 转换为 example/query 需要的格式
    values = []
    for arg in (arguments or []):
        values.append({"keyword": arg.get("keyword", ""), "values": arg.get("values", [])})

    body = {
        "chartsId": chart_id,
        "type": "SQL",
        "sql": detail["sql"],
        "dataSourceType": resolve_datasource(datasource_type),
        "arguments": detail.get("arguments", []),
        "values": values,
    }
    data = api_post("/charts/example/query", body=body, timeout=120).get("data", {})
    return _fmt_result(data, max_rows)


def batch_chart_details(chart_ids: list, from_dashboard_id="") -> dict:
    """批量查询图表详情（单次 API 调用）。"""
    body = {"chartsIds": chart_ids}
    if from_dashboard_id:
        body["fromDashboardId"] = from_dashboard_id
    result = api_post("/dashboard-query/detail/batch", body=body)
    data_list = result.get("data", [])
    details = {}
    for d in (data_list if isinstance(data_list, list) else []):
        if isinstance(d, dict) and d.get("id"):
            details[d["id"]] = d
    return details


def export_chart(chart_id: str, export_type="CSV", filename="", dashboard_id="",
                 arguments=None, sql="", datasource_type="") -> dict:
    """导出图表数据为 CSV/Excel。有 dashboard_id 走 dashboard-query 导出，否则走 charts 导出。"""
    et = export_type.upper()
    if et not in ("CSV", "EXCEL"):
        raise ValueError(f"exportType 必须是 CSV 或 EXCEL，实际: {et}")
    if dashboard_id:
        body = {"arguments": arguments or []}
        params = {"dashboardId": dashboard_id, "exportType": et}
        if filename:
            params["filename"] = filename
        result = api_post(f"/dashboard-query/charts/{chart_id}/export", body=body, params=params, timeout=120)
    else:
        body = {"id": chart_id, "chartType": "SQL", "exportType": et}
        if filename:
            body["filename"] = filename
        if sql:
            body["sql"] = sql
        if datasource_type:
            body["dataSourceType"] = resolve_datasource(datasource_type)
        result = api_post("/charts/export", body=body, timeout=120)
    return {"chartId": chart_id, "exportType": et, "result": result.get("data", result)}


def cancel_query(task_id: str) -> dict:
    """取消正在执行的查询任务。"""
    api_post(f"/charts/query/cancel/{task_id}")
    return {"taskId": task_id, "message": "查询已取消"}


def fork_chart(chart_id: str, chart_type="SQL") -> dict:
    """复制图表。"""
    result = api_post("/charts/fork", body={"id": chart_id, "type": chart_type})
    new_id = extract_id(result.get("data", ""))
    return {"sourceChartId": chart_id, "newChartId": new_id, "message": "图表复制成功"}


def save_argument_dependencies(chart_id: str, keywords: list, sql: str,
                               chart_type="SQL", old_keywords=None) -> dict:
    """保存参数依赖（参数联动 SQL）。"""
    body = {"id": chart_id, "chartType": chart_type, "keywords": keywords, "sql": sql}
    if old_keywords:
        body["oldKeywords"] = old_keywords
    api_post("/charts/argument/dependencies/save", body=body)
    return {"chartId": chart_id, "keywords": keywords, "message": "参数依赖保存成功"}


def get_argument_dependency_values(chart_id: str, sql: str, datasource_type="TRINO") -> dict:
    """获取参数依赖取值（执行联动 SQL 查询可选值）。"""
    body = {"chartsId": chart_id, "sql": sql, "sourceType": resolve_datasource(datasource_type)}
    result = api_post("/charts/argument/dependencies/values", body=body, timeout=60)
    return {"chartId": chart_id, "values": result.get("data", [])}


def delete_argument_dependencies(chart_id: str, keywords: list, chart_type="SQL") -> dict:
    """删除参数依赖。"""
    api_delete("/charts/argument/dependencies", body={"id": chart_id, "type": chart_type, "keywords": keywords})
    return {"chartId": chart_id, "deletedKeywords": keywords, "message": "参数依赖已删除"}


def batch_update_datasource(chart_ids: list, to_datasource: str) -> dict:
    """批量更新图表数据源。"""
    ds = resolve_datasource(to_datasource)
    api_post("/sql-lab/datasource/batch-update", body={"ids": chart_ids, "toDatasource": ds})
    return {"chartIds": chart_ids, "toDatasource": ds, "message": f"已将 {len(chart_ids)} 个图表数据源更新为 {ds}"}


def _fmt_result(data, max_rows) -> dict:
    if not isinstance(data, dict):
        return {"error": "unexpected format", "raw": data}
    columns = data.get("columns", data.get("header", []))
    all_rows = data.get("result", data.get("rows", data.get("data", [])))
    if not isinstance(all_rows, list):
        all_rows = []
    rows = all_rows[:max_rows]
    return {"columns": columns, "rows": rows, "totalRows": len(all_rows),
            "returnedRows": len(rows)}


def main():
    parser = argparse.ArgumentParser(description="图表操作")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("create")
    p.add_argument("--name", required=True)
    p.add_argument("--sql", default="")
    p.add_argument("--sql-file", default="")
    p.add_argument("--datasource", default="TRINO")
    p.add_argument("--catalog", default="hive")
    p.add_argument("--tags", default="")
    p.add_argument("--description", default="")

    p = sub.add_parser("update")
    p.add_argument("chart_id")
    p.add_argument("--name", default=None)
    p.add_argument("--sql", default=None)
    p.add_argument("--sql-file", default=None)
    p.add_argument("--datasource", default=None)
    p.add_argument("--catalog", default=None)
    p.add_argument("--tags", default=None)

    p = sub.add_parser("viz")
    p.add_argument("chart_id")
    p.add_argument("--type", required=True, dest="viz_type")
    p.add_argument("--name", default="")
    p.add_argument("--x-axis", default="")
    p.add_argument("--y-axis", default="")
    p.add_argument("--group", default="")
    p.add_argument("--dashboard", default="")
    # 轴配置
    p.add_argument("--x-axis-type", choices=["category", "time", "value", "log"], default="")
    p.add_argument("--x-axis-name", default="")
    p.add_argument("--x-axis-rotation", type=int, default=None)
    p.add_argument("--y-axis-name", default="")
    p.add_argument("--y-axis-min", type=float, default=None)
    p.add_argument("--y-axis-max", type=float, default=None)
    p.add_argument("--y-axis-format", default="")
    # 双Y轴
    p.add_argument("--y-axis-right", default="")
    p.add_argument("--y-axis-right-name", default="")
    # 系列
    p.add_argument("--series-type", default="")
    p.add_argument("--stacked", action="store_true", default=False)
    p.add_argument("--show-label", action="store_true", default=False)
    # Counter
    p.add_argument("--count-column", default="")
    p.add_argument("--target-column", default="")
    p.add_argument("--decimal-places", type=int, default=None)
    p.add_argument("--prefix", default="")
    p.add_argument("--suffix", default="")
    # Heatmap
    p.add_argument("--x-column", default="")
    p.add_argument("--y-column", default="")
    p.add_argument("--color-column", default="")
    # Funnel
    p.add_argument("--name-column", default="")
    p.add_argument("--value-column", default="")
    # 图例
    p.add_argument("--show-legend", dest="show_legend", action="store_true", default=None)
    p.add_argument("--no-show-legend", dest="show_legend", action="store_false")
    # Pivot Table
    p.add_argument("--show-totals", action="store_true", default=False)
    # JSON 透传
    p.add_argument("--options-json", default="")

    p = sub.add_parser("detail")
    p.add_argument("chart_id")
    p.add_argument("--from-dashboard", default="")

    p = sub.add_parser("query")
    p.add_argument("chart_id", nargs="?", default="")
    p.add_argument("--batch", default="")
    p.add_argument("--dashboard", default="")
    p.add_argument("--datasource", default="", help="临时覆盖数据源执行（走 example/query 接口）")
    p.add_argument("--args", default="{}")
    p.add_argument("--async", dest="use_async", action="store_true")
    p.add_argument("--no-cache", dest="use_cache", action="store_false")
    p.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)

    # 导出
    p = sub.add_parser("export", help="导出图表数据为 CSV/Excel")
    p.add_argument("chart_id")
    p.add_argument("--type", dest="export_type", default="CSV", choices=["CSV", "EXCEL"])
    p.add_argument("--filename", default="")
    p.add_argument("--dashboard", default="")
    p.add_argument("--args", default="{}")

    # 取消查询
    p = sub.add_parser("cancel", help="取消正在执行的查询任务")
    p.add_argument("task_id")

    # 复制图表
    p = sub.add_parser("fork", help="复制图表")
    p.add_argument("chart_id")

    # 参数依赖
    p = sub.add_parser("arg-dep-save", help="保存参数依赖（参数联动 SQL）")
    p.add_argument("chart_id")
    p.add_argument("--keywords", required=True, help="依赖的参数关键字，逗号分隔")
    p.add_argument("--sql", required=True)
    p.add_argument("--old-keywords", default="", help="替换已有依赖的关键字，逗号分隔")

    p = sub.add_parser("arg-dep-values", help="获取参数依赖取值")
    p.add_argument("chart_id")
    p.add_argument("--sql", required=True)
    p.add_argument("--datasource", default="TRINO")

    p = sub.add_parser("arg-dep-delete", help="删除参数依赖")
    p.add_argument("chart_id")
    p.add_argument("--keywords", required=True, help="要删除的关键字，逗号分隔")

    # 批量详情
    p = sub.add_parser("batch-detail", help="批量查询图表详情")
    p.add_argument("chart_ids", nargs="+")
    p.add_argument("--from-dashboard", default="")

    # 批量更新数据源
    p = sub.add_parser("batch-update-ds", help="批量更新图表数据源")
    p.add_argument("chart_ids", nargs="+")
    p.add_argument("--datasource", required=True)

    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        sys.exit(1)

    try:
        if args.action == "create":
            sql = _resolve_sql(args)
            if not sql: print_error("请通过 --sql 或 --sql-file 提供 SQL"); sys.exit(1)
            result = create_chart(name=args.name, sql=sql, datasource_type=args.datasource,
                                  catalog=args.catalog, tags=parse_tags(args.tags), description=args.description)

        elif args.action == "update":
            sql = _resolve_sql(args)
            result = update_chart(chart_id=args.chart_id, name=args.name, sql=sql,
                                  datasource_type=args.datasource, catalog=args.catalog,
                                  tags=parse_tags(args.tags) if args.tags else None)

        elif args.action == "viz":
            if args.options_json:
                opts = parse_json_arg(args.options_json)
            else:
                opts = {}
                if args.x_axis: opts["xAxis"] = args.x_axis
                if args.y_axis: opts["yAxises"] = [y.strip() for y in args.y_axis.split(",") if y.strip()]
                if args.group: opts["group"] = args.group
                if args.stacked: opts["stack"] = True
                if args.show_label: opts["showLabel"] = True
                # X 轴配置
                x_cfg = {}
                if args.x_axis_type: x_cfg["type"] = args.x_axis_type
                if args.x_axis_name: x_cfg["name"] = args.x_axis_name
                if args.x_axis_rotation is not None: x_cfg["rotate"] = args.x_axis_rotation
                if x_cfg: opts["xAxisOption"] = x_cfg
                # Y 轴配置（平台格式：yAxisOption.left / yAxisOption.right）
                y_left = {"type": "value"}
                if args.y_axis_name: y_left["name"] = args.y_axis_name
                if args.y_axis_min is not None: y_left["min"] = args.y_axis_min
                if args.y_axis_max is not None: y_left["max"] = args.y_axis_max
                if args.y_axis_format: y_left["format"] = {"number": args.y_axis_format}
                y_right = {"type": "value"}
                if args.y_axis_right:
                    opts["yAxisRight"] = [y.strip() for y in args.y_axis_right.split(",") if y.strip()]
                    if args.y_axis_right_name: y_right["name"] = args.y_axis_right_name
                if args.y_axis_name or args.y_axis_min is not None or args.y_axis_max is not None or args.y_axis_format or args.y_axis_right:
                    opts["yAxisOption"] = {"left": y_left, "right": y_right}
                # 系列类型覆盖 (格式: "col1:line,col2:bar")
                if args.series_type:
                    y_right = opts.get("yAxisRight", [])
                    series_opts = {}
                    for pair in args.series_type.split(","):
                        col, stype = pair.split(":")
                        col, stype = col.strip(), stype.strip()
                        entry = {"zIndex": 0}
                        if stype.lower() != opts.get("type", ""):
                            entry["type"] = stype.lower()
                        entry["yAxis"] = 1 if col in y_right else 0
                        series_opts[col] = entry
                    opts["seriesOptions"] = series_opts
                # Counter
                if args.count_column: opts["countColumn"] = args.count_column
                if args.target_column: opts["targetColumn"] = args.target_column
                if args.decimal_places is not None: opts["decimalPlaces"] = args.decimal_places
                if args.prefix: opts["prefix"] = args.prefix
                if args.suffix: opts["suffix"] = args.suffix
                # Heatmap
                if args.x_column: opts["xColumn"] = args.x_column
                if args.y_column: opts["yColumn"] = args.y_column
                if args.color_column: opts["colorColumn"] = args.color_column
                # Funnel
                if args.name_column: opts["nameColumn"] = args.name_column
                if args.value_column: opts["valueColumn"] = args.value_column
                # Pivot Table
                if args.show_totals: opts["showTotals"] = True
                # showLegend: 折线/柱状/面积等 CHART 类型默认显示图例
                if args.show_legend is not None:
                    opts["showLegend"] = args.show_legend
                elif args.viz_type.upper() in CHART_SUB_TYPES:
                    opts["showLegend"] = True
            result = create_visualization(chart_id=args.chart_id, viz_type=args.viz_type,
                                          viz_name=args.name, options=opts or None,
                                          from_dashboard_id=args.dashboard)

        elif args.action == "detail":
            result = get_chart_detail(chart_id=args.chart_id, from_dashboard_id=args.from_dashboard)

        elif args.action == "query":
            ad = parse_json_arg(args.args)
            arguments = build_arguments(ad) if ad else []
            if not arguments and args.dashboard:
                arguments = _build_dashboard_arguments(args.dashboard)
            if args.datasource and args.chart_id:
                result = example_query(chart_id=args.chart_id, datasource_type=args.datasource,
                                       arguments=arguments, max_rows=args.max_rows)
            elif args.batch:
                cids = [c.strip() for c in args.batch.split(",") if c.strip()]
                result = query_charts_batch(chart_ids=cids, dashboard_id=args.dashboard,
                                            arguments=arguments, use_cache=args.use_cache, max_rows=args.max_rows)
            elif args.chart_id:
                result = query_chart(chart_id=args.chart_id, dashboard_id=args.dashboard,
                                     arguments=arguments, use_async=args.use_async,
                                     use_cache=args.use_cache, max_rows=args.max_rows)
            else:
                parser.print_help(); sys.exit(1)

        elif args.action == "export":
            ad = parse_json_arg(args.args)
            arguments = build_arguments(ad) if ad else []
            result = export_chart(chart_id=args.chart_id, export_type=args.export_type,
                                  filename=args.filename, dashboard_id=args.dashboard,
                                  arguments=arguments)

        elif args.action == "cancel":
            result = cancel_query(task_id=args.task_id)

        elif args.action == "fork":
            result = fork_chart(chart_id=args.chart_id)

        elif args.action == "arg-dep-save":
            kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
            old_kws = [k.strip() for k in args.old_keywords.split(",") if k.strip()] if args.old_keywords else None
            result = save_argument_dependencies(chart_id=args.chart_id, keywords=kws,
                                                sql=args.sql, old_keywords=old_kws)

        elif args.action == "arg-dep-values":
            result = get_argument_dependency_values(chart_id=args.chart_id, sql=args.sql,
                                                    datasource_type=args.datasource)

        elif args.action == "arg-dep-delete":
            kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
            result = delete_argument_dependencies(chart_id=args.chart_id, keywords=kws)

        elif args.action == "batch-detail":
            result = batch_chart_details(chart_ids=args.chart_ids,
                                         from_dashboard_id=args.from_dashboard)

        elif args.action == "batch-update-ds":
            result = batch_update_datasource(chart_ids=args.chart_ids,
                                             to_datasource=args.datasource)

        else:
            parser.print_help(); sys.exit(1)

        print_result(result)
    except json.JSONDecodeError as e:
        print_error(f"JSON 解析失败: {e}"); sys.exit(1)
    except Exception as e:
        print_error(str(e)); sys.exit(1)


if __name__ == "__main__":
    main()
