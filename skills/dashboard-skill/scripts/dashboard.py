#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dashboard 业务逻辑：详情、创建、克隆修改、权限分享、可访问列表查询、参数源检查。"""

from __future__ import annotations

import argparse
import sys
from typing import List

from _api import (
    DASHBOARD_WEB_URL,
    api_batch_get, api_get, api_post, api_put,
    extract_creator, extract_id, parse_json_arg,
    parse_tags, print_error, print_result,
)


# ========== Dashboard 详情查询 ==========

def get_dashboard_detail(dashboard_id: str, include_charts: bool = False) -> dict:
    """获取 Dashboard 详情"""
    result = api_get(f"/dashboard-mgr/{dashboard_id}")
    data = result.get("data", result)

    info = {
        "id": data.get("id", dashboard_id),
        "name": data.get("name", ""),
        "url": f"{DASHBOARD_WEB_URL}/{dashboard_id}",
        "description": data.get("description", ""),
        "customTags": data.get("customTags"),
        "createdAt": data.get("createdAt", ""),
        "updatedAt": data.get("updatedAt", ""),
        "permission": data.get("permission", 0),
        "autoQuery": (data.get("options") or {}).get("autoQuery"),
    }

    info.update(extract_creator(data))
    raw_params = data.get("parameters") or []
    info["parameters"] = [
        {k: p[k] for k in ("key", "title", "type", "defaultValues", "source", "sourceId",
                            "quotation", "multipleValue", "widgetParams") if k in p}
        for p in raw_params
    ]
    info["paramConfigs"] = data.get("paramConfigs") or []

    pure_widgets = []
    for w in (data.get("widgets") or []):
        pure_widgets.append({
            "widgetId": w.get("id"),
            "type": w.get("type", "CHART"),
            "chartsId": w.get("chartsId"),
            "text": w.get("text")
        })
    info["widgets"] = pure_widgets

    if include_charts:
        chart_ids = list({w.get("chartsId") for w in (data.get("widgets") or []) if w.get("chartsId")})
        if chart_ids:
            chart_results = api_batch_get([f"/charts/detail/{cid}" for cid in chart_ids])
            charts_info = {}
            for cid, res in zip(chart_ids, chart_results):
                cd = res.get("data", res)
                if isinstance(cd, dict):
                    charts_info[cid] = {
                        "name": cd.get("name", ""),
                        "sql": cd.get("sql", ""),
                        "dataSourceType": cd.get("dataSourceType", ""),
                        "arguments": cd.get("arguments", []),
                        "visualizations": cd.get("visualizations", []),
                    }
            info["charts"] = charts_info

    return info


# ========== Dashboard 核心 CRUD ==========

def create_dashboard(name: str, description: str = "", tags: list = None, auto_query: bool = False) -> dict:
    body = {"name": name, "description": description, "customTags": tags or []}
    result = api_post("/dashboard-mgr", body=body)
    did = extract_id(result.get("data", ""))
    if not auto_query:
        try:
            api_put(f"/dashboard-mgr/{did}", body={
                "id": did, "name": name, "description": description,
                "customTags": tags or [], "options": {"autoQuery": False},
                "widgets": [], "parameters": [], "paramConfigs": [],
            })
        except Exception as e:
            return {"dashboardId": did, "name": name, "url": f"{DASHBOARD_WEB_URL}/{did}",
                    "message": "创建成功", "warning": f"关闭 autoQuery 失败: {e}"}
    return {"dashboardId": did, "name": name, "url": f"{DASHBOARD_WEB_URL}/{did}", "message": "创建成功"}


def update_dashboard(dashboard_id: str, name: str = None, description: str = None,
                     tags: list = None, param_configs: list = None,
                     parameters: list = None, auto_query: bool = None) -> dict:
    detail = api_get(f"/dashboard-mgr/{dashboard_id}").get("data", {})

    options = detail.get("options") or {}
    if auto_query is not None:
        options["autoQuery"] = auto_query

    body = {
        "id": dashboard_id,
        "name": name if name is not None else detail.get("name"),
        "description": description if description is not None else detail.get("description"),
        "customTags": tags if tags is not None else (detail.get("customTags") or []),
        "parameters": parameters if parameters is not None else (detail.get("parameters") or []),
        "options": options,
        "widgets": detail.get("widgets") or []
    }

    api_put(f"/dashboard-mgr/{dashboard_id}", body=body)

    if param_configs is not None:
        api_post("/dashboard-mgr/update/param/config", body={
            "dashboardId": dashboard_id, "paramConfigs": param_configs,
        })

    return {"dashboardId": dashboard_id, "message": "更新成功"}


def fork_dashboard(source_id: str, with_charts: bool = True) -> dict:
    if with_charts:
        result = api_post(f"/dashboard-mgr/fork/and/charts/{source_id}")
    else:
        result = api_post(f"/dashboard-mgr/fork/{source_id}")
    new_id = extract_id(result.get("data", ""))
    return {"dashboardId": new_id, "url": f"{DASHBOARD_WEB_URL}/{new_id}", "message": "Fork 成功"}


def clone_and_modify(source_id: str, new_name: str, sql_replacements: dict = None, new_date_range: list = None) -> dict:
    """克隆 Dashboard 并修改：Fork(含图表) → 重命名 → 替换 SQL → 更新日期参数。"""
    warnings = []

    fork_result = fork_dashboard(source_id, with_charts=True)
    new_id = fork_result["dashboardId"]

    raw = api_get(f"/dashboard-mgr/{new_id}").get("data", {})

    if sql_replacements:
        chart_ids = list({w.get("chartsId") for w in (raw.get("widgets") or []) if w.get("chartsId")})
        if chart_ids:
            chart_results = api_batch_get([f"/charts/detail/{cid}" for cid in chart_ids])
            for cid, res in zip(chart_ids, chart_results):
                cd = res.get("data", res)
                if not isinstance(cd, dict) or not cd.get("sql"):
                    continue
                new_sql = cd["sql"]
                for old_str, new_str in sql_replacements.items():
                    new_sql = new_sql.replace(old_str, new_str)
                if new_sql != cd["sql"]:
                    try:
                        sb = {"id": cid, "type": "SQL", "sql": new_sql,
                              "dataSourceType": cd.get("dataSourceType", "TRINO"),
                              "catalog": cd.get("catalog", "hive"),
                              "arguments": cd.get("arguments", [])}
                        api_put(f"/sql-lab/{cid}", body=sb)
                    except Exception as e:
                        warnings.append(f"图表 {cid} SQL 替换失败: {e}")

    update_kwargs = {"name": new_name}
    if new_date_range and isinstance(new_date_range, list) and len(new_date_range) >= 2:
        param_configs = raw.get("paramConfigs") or []
        for pc in param_configs:
            if any(kw in pc.get("key", "").lower() for kw in ("date", "dt", "日期")):
                pc["values"] = new_date_range[:2]
        update_kwargs["param_configs"] = param_configs

    update_dashboard(new_id, **update_kwargs)

    return {
        "dashboardId": new_id, "name": new_name,
        "url": f"{DASHBOARD_WEB_URL}/{new_id}",
        "warnings": warnings, "message": "克隆与修改完成"
    }


# ========== 工具函数 ==========

def _calc_max_bottom(widgets: list) -> int:
    """计算 widgets 布局的最大底部 y 坐标。"""
    max_bottom = 0
    for w in widgets:
        pos = (w.get("options") or {}).get("position", {})
        bottom = pos.get("y", 0) + pos.get("h", 0)
        if bottom > max_bottom:
            max_bottom = bottom
    return max_bottom


# ========== 批量操作机制 (支持部分成功/容错) ==========

def add_charts_to_dashboard(dashboard_id: str, chart_ids: List[str]) -> dict:
    """将多个图表加入看板。通过读取→追加→全量更新 widgets 实现。"""
    raw = api_get(f"/dashboard-mgr/{dashboard_id}").get("data", {})
    widgets = raw.get("widgets") or []

    max_bottom = _calc_max_bottom(widgets)

    existing_chart_ids = {w.get("chartsId") for w in widgets if w.get("chartsId")}
    success_ids = []
    errors = []

    for cid in chart_ids:
        if cid in existing_chart_ids:
            errors.append({"chartId": cid, "error": "图表已存在于看板中"})
            continue
        try:
            detail = api_get(f"/charts/detail/{cid}").get("data", {})
            viz_list = detail.get("visualizations") or []
            viz_id = viz_list[-1].get("id", "") if viz_list else ""

            # 根据图表类型动态设定 widget 尺寸
            viz_type = ""
            if viz_list:
                viz_opts = viz_list[-1].get("options") or {}
                viz_type = viz_opts.get("type", "")
            if viz_type in ("pie", "counter"):
                w, h = 3, 11
            elif viz_type == "":
                # TABLE / PIVOT_TABLE（type 在上层，不在 options.type）
                w, h = 6, 11
            else:
                # line / bar / area / scatter / boxplot / heatmap / funnel
                w, h = 6, 10

            widget_params = []
            for arg in (detail.get("arguments") or []):
                kw = arg.get("keyword", "")
                if kw:
                    widget_params.append({
                        "keyword": kw,
                        "title": arg.get("title", kw),
                        "defaultValues": arg.get("defaultValues") or [],
                        "level": "widget",
                        "source": "CUSTOM",
                    })

            new_widget = {
                "dashboardId": dashboard_id,
                "chartsId": cid,
                "visualizationId": viz_id,
                "type": detail.get("type", "SQL"),
                "text": "",
                "parameters": widget_params,
                "options": {"position": {"x": 0, "y": max_bottom, "w": w, "h": h}},
            }
            widgets.append(new_widget)
            max_bottom += h
            success_ids.append(cid)
        except Exception as e:
            errors.append({"chartId": cid, "error": str(e)})

    if success_ids:
        update_body = {
            "id": dashboard_id,
            "name": raw.get("name"),
            "description": raw.get("description"),
            "customTags": raw.get("customTags"),
            "parameters": raw.get("parameters") or [],
            "paramConfigs": raw.get("paramConfigs") or [],
            "options": raw.get("options") or {},
            "widgets": widgets,
        }
        api_put(f"/dashboard-mgr/{dashboard_id}", body=update_body)

    return {
        "dashboardId": dashboard_id,
        "successCount": len(success_ids),
        "successIds": success_ids,
        "errors": errors
    }


def add_text_to_dashboard(dashboard_id: str, text: str, width: int = 6, height: int = 2,
                          center: bool = True) -> dict:
    """添加文字说明（Markdown）组件到 Dashboard。"""
    raw = api_get(f"/dashboard-mgr/{dashboard_id}").get("data", {})
    widgets = raw.get("widgets") or []

    max_bottom = _calc_max_bottom(widgets)

    display_text = f'<center><font style="font-size: 24px;">{text}</font></center>' if center else text
    new_widget = {
        "dashboardId": dashboard_id,
        "text": display_text, "type": None, "chartsId": None,
        "options": {"position": {"x": 0, "y": max_bottom, "w": width, "h": height}}
    }
    widgets.append(new_widget)

    update_body = {
        "id": dashboard_id, "name": raw.get("name"),
        "description": raw.get("description"), "customTags": raw.get("customTags"),
        "parameters": raw.get("parameters"), "paramConfigs": raw.get("paramConfigs"),
        "options": raw.get("options"), "widgets": widgets,
    }
    api_put(f"/dashboard-mgr/{dashboard_id}", body=update_body)
    return {"dashboardId": dashboard_id, "message": "已添加文字组件"}


def share_dashboard(dashboard_id: str, user_ids: List[str], permission: int = 1, share_charts: bool = True) -> dict:
    body = [{"userId": int(uid), "permission": permission, "shareCharts": share_charts}
            for uid in user_ids]
    try:
        api_post(f"/dashboard-shared/shared/{dashboard_id}/user", body=body)
        return {
            "dashboardId": dashboard_id,
            "successCount": len(user_ids),
            "successIds": list(user_ids),
            "errors": []
        }
    except Exception as e:
        return {
            "dashboardId": dashboard_id,
            "successCount": 0,
            "successIds": [],
            "errors": [{"userIds": list(user_ids), "error": str(e)}]
        }


def cancel_share(dashboard_id: str, user_id: str) -> dict:
    api_post(f"/dashboard-shared/cancel-shared/dashboard/{dashboard_id}/user/{user_id}")
    return {"dashboardId": dashboard_id, "canceledUserId": user_id, "message": "已取消分享"}


def list_shared_users(dashboard_id: str) -> dict:
    result = api_get(f"/dashboard-shared/shared-users/dashboard/{dashboard_id}")
    raw = result.get("data", [])
    slim = []
    for u in (raw if isinstance(raw, list) else []):
        item = {}
        if u.get("id"): item["userId"] = u["id"]
        if u.get("name"): item["name"] = u["name"]
        elif u.get("email"): item["name"] = u["email"]
        if u.get("permission") is not None: item["permission"] = u["permission"]
        slim.append(item)
    return {"dashboardId": dashboard_id, "sharedUsers": slim}


# ========== 用户搜索 ==========

_PERMISSION_LABELS = {1: "查看", 2: "编辑", 3: "查看+编辑", 5: "查看+分享", 7: "查看+编辑+分享"}


def user_dashboards(keyword: str) -> dict:
    """查询指定用户拥有和被分享的所有 Dashboard（按姓名/邮箱搜索）。"""
    found = search_user(keyword)
    users = found.get("users", [])
    if not users:
        return {"keyword": keyword, "message": f"未找到匹配 '{keyword}' 的用户"}

    unique_names = {u["name"] for u in users}
    if len(users) > 1 and len(unique_names) > 1:
        return {"keyword": keyword, "message": f"匹配到 {len(users)} 个不同用户，请使用更精确的关键词",
                "candidates": users}

    uids = list({u["userId"] for u in users})
    # 校验 userId 必须为纯数字，防止 SQL 注入
    for uid in uids:
        if not str(uid).isdigit():
            return {"keyword": keyword, "message": f"用户 ID 格式异常: {uid}"}
    uid_list = ", ".join(str(u) for u in uids)
    uid_condition = f"= {uids[0]}" if len(uids) == 1 else f"IN ({uid_list})"
    user = users[0]
    sql = (
        f'SELECT CAST(d._id AS VARCHAR) as dashboard_id, d.name, '
        f'CASE WHEN d.createdby {uid_condition} THEN \'owner\' ELSE \'shared\' END as access_type, '
        f'COALESCE(sh.permission, 0) as permission '
        f'FROM mongodb."datain-prod"."dashboard" d '
        f'LEFT JOIN ('
        f'  SELECT CAST(ds.dashboardid AS VARCHAR) as did, permission '
        f'  FROM mongodb."datain-prod"."dashboard-shared" ds '
        f'  CROSS JOIN UNNEST(ds.shares) AS t(sharedat, byshared, permission, userid) '
        f'  WHERE userid {uid_condition}'
        f') sh ON CAST(d._id AS VARCHAR) = sh.did '
        f'WHERE d.createdby {uid_condition} OR sh.did IS NOT NULL'
    )
    result = api_post("/sql-lab/sql/execute", body={"sql": sql, "datasource": "TRINO"}, timeout=120)
    rows = result.get("data") or []

    dashboards = []
    for r in rows:
        did = r.get("dashboard_id", "")
        perm = r.get("permission", 0)
        dashboards.append({
            "id": did,
            "name": r.get("name", ""),
            "url": f"{DASHBOARD_WEB_URL}/{did}",
            "accessType": "自建" if r.get("access_type") == "owner" else "被分享",
            "permission": _PERMISSION_LABELS.get(perm, str(perm)),
        })

    owned = [d for d in dashboards if d["accessType"] == "自建"]
    shared = [d for d in dashboards if d["accessType"] == "被分享"]
    return {
        "user": user,
        "ownedCount": len(owned),
        "sharedCount": len(shared),
        "totalCount": len(dashboards),
        "dashboards": dashboards,
    }


def search_user(keyword: str, limit: int = 20) -> dict:
    """通过姓名或邮箱模糊搜索平台用户（查询 MongoDB 用户表）。"""
    safe_kw = keyword.replace("'", "''").replace("%", "\\%").replace("_", "\\_")
    sql = (
        f'SELECT _id as user_id, name, email '
        f'FROM mongodb."datain-prod"."user" '
        f"WHERE name LIKE '%{safe_kw}%' ESCAPE '\\' OR email LIKE '%{safe_kw}%' ESCAPE '\\' "
        f"LIMIT {int(limit)}"
    )
    result = api_post("/sql-lab/sql/execute", body={"sql": sql, "datasource": "TRINO"}, timeout=60)
    users = result.get("data") or []
    slim = [{"userId": u.get("user_id"), "name": u.get("name", ""), "email": u.get("email", "")}
            for u in users if u.get("user_id")]
    info = {"keyword": keyword, "count": len(slim), "users": slim}
    if len(slim) >= limit:
        info["message"] = f"结果已截断（上限{limit}），请使用更精确的关键词"
    return info


# ========== 可访问性与参数检查 ==========

def list_accessible_dashboards(keyword: str = None) -> dict:
    """查询当前用户可访问的 Dashboard 列表（精简输出，节省 Token）。"""
    params = {"keyword": keyword} if keyword else {}
    result = api_get("/dashboard-mgr/query/accessible", params=params)
    data = result.get("data", [])

    slim = []
    for d in data:
        item = {"name": d.get("name", "")}
        if d.get("id"):
            item["id"] = d["id"]
        if d.get("tags"):
            item["tags"] = d["tags"]
        updater = d.get("updater") or {}
        if isinstance(updater, dict) and updater.get("name"):
            item["updater"] = updater["name"]
        slim.append(item)

    return {"count": len(slim), "keyword": keyword, "dashboards": slim}


def check_widget_parameters(dashboard_id: str) -> dict:
    """检查 Dashboard 中图表的参数源配置情况，重点提纯存在缺失的组件。"""
    result = api_get(f"/dashboard-mgr/widgets/parameter-check/{dashboard_id}")
    data = result.get("data", [])
    
    # 提纯：为 AI Agent 筛选出真正存在问题的 widget
    problematic_widgets = [w for w in data if w.get("missingArguments")]
    
    return {
        "dashboardId": dashboard_id,
        "totalWidgetsChecked": len(data),
        "problematicCount": len(problematic_widgets),
        "problematicWidgets": problematic_widgets
    }


def config_params(dashboard_id: str) -> dict:
    """自动配置 Dashboard 参数源：读取所有图表参数 → 统一提升为全局参数 → 初始化 paramConfigs。"""
    raw = api_get(f"/dashboard-mgr/{dashboard_id}").get("data", {})
    widgets = raw.get("widgets") or []

    chart_widgets = []
    for w in widgets:
        cid = w.get("chartsId")
        vid = w.get("visualizationId") or (w.get("visualization") or {}).get("id", "")
        if cid:
            chart_widgets.append((w, cid, vid))

    if not chart_widgets:
        return {"dashboardId": dashboard_id, "message": "无需配置参数源（没有图表组件）"}

    unique_chart_ids = list({cw[1] for cw in chart_widgets})
    chart_results = api_batch_get([f"/charts/detail/{cid}" for cid in unique_chart_ids])
    chart_details = {}
    for cid, res in zip(unique_chart_ids, chart_results):
        d = res.get("data", res)
        if isinstance(d, dict) and "arguments" in d:
            chart_details[cid] = d

    param_map = {}
    for w, cid, vid in chart_widgets:
        detail = chart_details.get(cid, {})
        for arg in (detail.get("arguments") or []):
            kw = arg.get("keyword", "")
            if not kw:
                continue
            if kw not in param_map:
                p = {"key": kw, "title": arg.get("title", kw),
                     "type": arg.get("type", "TEXT"),
                     "defaultValues": arg.get("defaultValues", []),
                     "widgetParams": []}
                for field in ("source", "sourceId", "dataType", "quotation",
                              "multipleValue", "preselected"):
                    if arg.get(field) is not None:
                        p[field] = arg[field]
                param_map[kw] = p
            existing_wps = {(wp["visualizationId"], wp["keyword"])
                            for wp in param_map[kw]["widgetParams"]}
            if vid and (vid, kw) not in existing_wps:
                param_map[kw]["widgetParams"].append(
                    {"visualizationId": vid, "keyword": kw})

    global_params = list(param_map.values())

    param_configs = [{"key": p["key"], "isShow": True,
                      "values": p.get("defaultValues", [])} for p in global_params]

    for w, cid, vid in chart_widgets:
        detail = chart_details.get(cid, {})
        wp_list = []
        for arg in (detail.get("arguments") or []):
            kw = arg.get("keyword", "")
            if not kw:
                continue
            wp_list.append({
                "keyword": kw,
                "title": arg.get("title", kw),
                "defaultValues": arg.get("defaultValues") or [],
                "level": "dashboard",
                "source": kw,
            })
        w["parameters"] = wp_list

    update_body = {
        "id": dashboard_id, "name": raw.get("name"),
        "description": raw.get("description"), "customTags": raw.get("customTags"),
        "parameters": global_params,
        "options": raw.get("options"), "widgets": widgets,
    }
    put_resp = api_put(f"/dashboard-mgr/{dashboard_id}", body=update_body)

    if param_configs:
        api_post("/dashboard-mgr/update/param/config", body={
            "dashboardId": dashboard_id, "paramConfigs": param_configs,
        })

    put_data = put_resp.get("data", {}) if isinstance(put_resp, dict) else {}

    saved_params = put_data.get("parameters", []) if isinstance(put_data, dict) else []
    widget_params_summary = {}
    for sp in saved_params:
        kw = sp.get("key", "")
        wps = sp.get("widgetParams", [])
        if kw and wps:
            widget_params_summary[kw] = len(wps)

    result = {
        "dashboardId": dashboard_id,
        "globalParams": [p["key"] for p in global_params],
        "widgetParamsBindings": widget_params_summary,
        "message": f"参数源配置完成，{len(global_params)} 个全局参数",
    }
    return result


# ========== CLI 路由入口 ==========

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashboard 业务逻辑")
    sub = parser.add_subparsers(dest="action")

    # detail
    p = sub.add_parser("detail", help="获取看板详情")
    p.add_argument("dashboard_id")
    p.add_argument("--include-charts", action="store_true")

    # create
    p = sub.add_parser("create", help="创建看板")
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--auto-query", action="store_true", default=False)

    # update
    p = sub.add_parser("update", help="更新看板")
    p.add_argument("dashboard_id")
    p.add_argument("--name")
    p.add_argument("--description")
    p.add_argument("--tags")
    p.add_argument("--param-configs", help="筛选器当前值配置(JSON)")
    p.add_argument("--parameters", help="Dashboard 级别 parameters 全量替换(JSON)")
    aq = p.add_mutually_exclusive_group()
    aq.add_argument("--auto-query", dest="auto_query", action="store_true", default=None)
    aq.add_argument("--no-auto-query", dest="auto_query", action="store_false")

    # fork
    p = sub.add_parser("fork", help="复制看板")
    p.add_argument("source_id")
    p.add_argument("--no-charts", dest="with_charts", action="store_false", default=True)

    # clone-and-modify
    p = sub.add_parser("clone-and-modify", help="克隆并修改看板")
    p.add_argument("source_id")
    p.add_argument("--name", required=True)
    p.add_argument("--sql-mapping", default="", help="SQL映射替换字典(JSON格式)")
    p.add_argument("--date-range", default="", help="新日期范围(JSON格式)")

    # add-chart
    p = sub.add_parser("add-chart", help="批量添加图表到看板")
    p.add_argument("dashboard_id")
    p.add_argument("chart_ids", nargs="+", help="一个或多个图表ID")

    # search-user / user-dashboards
    p = sub.add_parser("search-user", help="按姓名/邮箱搜索平台用户")
    p.add_argument("keyword", help="搜索关键词（姓名或邮箱）")

    p = sub.add_parser("user-dashboards", help="查询用户拥有和被分享的所有 Dashboard")
    p.add_argument("keyword", help="用户姓名或邮箱")

    # share / cancel-share / shared-users
    p = sub.add_parser("share", help="分享看板")
    p.add_argument("dashboard_id")
    p.add_argument("user_ids", nargs="*", help="被分享人ID列表")
    p.add_argument("--name", default="", help="按姓名搜索用户后分享（替代直接传 user_id）")
    p.add_argument("--permission", type=int, default=1, help="1=查看, 2=编辑, 3=编辑+分享")
    p.add_argument("--no-share-charts", dest="share_charts", action="store_false")
    
    p = sub.add_parser("cancel-share", help="取消分享")
    p.add_argument("dashboard_id")
    p.add_argument("user_id")

    p = sub.add_parser("shared-users", help="查看已分享用户")
    p.add_argument("dashboard_id")

    # [新增] accessible / parameter-check
    p = sub.add_parser("accessible", help="查询当前用户可访问的 Dashboard 列表")
    p.add_argument("--keyword", help="按名称、标签搜索(忽略大小写)")

    p = sub.add_parser("parameter-check", help="检查看板中组件的参数源配置")
    p.add_argument("dashboard_id")

    # config-params
    p = sub.add_parser("config-params", help="自动配置 Dashboard 参数源（add-chart 后必须执行）")
    p.add_argument("dashboard_id")

    # add-text
    p = sub.add_parser("add-text", help="添加文字说明组件到看板")
    p.add_argument("dashboard_id")
    p.add_argument("--text", required=True, help="Markdown 格式文字内容")
    p.add_argument("--width", type=int, default=6, help="组件宽度(1-6, 默认6满行)")
    p.add_argument("--height", type=int, default=2, help="组件高度(默认2)")
    p.add_argument("--no-center", dest="center", action="store_false", default=True, help="不居中显示")

    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        sys.exit(1)

    try:
        if args.action == "detail":
            result = get_dashboard_detail(args.dashboard_id, include_charts=args.include_charts)
            
        elif args.action == "create":
            result = create_dashboard(name=args.name, description=args.description,
                                      tags=parse_tags(args.tags), auto_query=args.auto_query)
            
        elif args.action == "update":
            result = update_dashboard(
                dashboard_id=args.dashboard_id,
                name=args.name,
                description=args.description,
                tags=parse_tags(args.tags) if args.tags else None,
                param_configs=parse_json_arg(args.param_configs) if args.param_configs else None,
                parameters=parse_json_arg(args.parameters) if args.parameters else None,
                auto_query=args.auto_query,
            )
            
        elif args.action == "fork":
            result = fork_dashboard(source_id=args.source_id, with_charts=args.with_charts)
            
        elif args.action == "clone-and-modify":
            result = clone_and_modify(
                source_id=args.source_id, 
                new_name=args.name,
                sql_replacements=parse_json_arg(args.sql_mapping) if args.sql_mapping else {},
                new_date_range=parse_json_arg(args.date_range) if args.date_range else None
            )
            
        elif args.action == "add-chart":
            result = add_charts_to_dashboard(args.dashboard_id, args.chart_ids)
            
        elif args.action == "search-user":
            result = search_user(args.keyword)

        elif args.action == "user-dashboards":
            result = user_dashboards(args.keyword)

        elif args.action == "share":
            user_ids = args.user_ids or []
            if args.name and not user_ids:
                found = search_user(args.name)
                users = found.get("users", [])
                if not users:
                    result = {"error": True, "message": f"未找到匹配 '{args.name}' 的用户"}
                elif len(users) == 1:
                    user_ids = [str(users[0]["userId"])]
                    result = share_dashboard(args.dashboard_id, user_ids,
                                             permission=args.permission, share_charts=args.share_charts)
                    result["matchedUser"] = users[0]
                else:
                    result = {"error": True,
                              "message": f"匹配到 {len(users)} 个用户，请指定具体 user_id",
                              "candidates": users}
            elif user_ids:
                result = share_dashboard(args.dashboard_id, user_ids,
                                         permission=args.permission, share_charts=args.share_charts)
            else:
                result = {"error": True, "message": "需要提供 user_ids 或 --name 参数"}
            
        elif args.action == "cancel-share":
            result = cancel_share(args.dashboard_id, args.user_id)
            
        elif args.action == "shared-users":
            result = list_shared_users(args.dashboard_id)

        elif args.action == "accessible":
            result = list_accessible_dashboards(keyword=args.keyword)
            
        elif args.action == "parameter-check":
            result = check_widget_parameters(args.dashboard_id)

        elif args.action == "config-params":
            result = config_params(args.dashboard_id)

        elif args.action == "add-text":
            result = add_text_to_dashboard(args.dashboard_id, text=args.text,
                                           width=args.width, height=args.height,
                                           center=args.center)

        else:
            parser.print_help()
            sys.exit(1)

        print_result(result)

    except Exception as e:
        # 统一的全局错误拦截，Agent 会收到友好的 JSON error
        print_error(str(e))