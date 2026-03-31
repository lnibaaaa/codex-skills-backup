#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cube 图表操作：创建、配置维度/指标、查询、添加到 Dashboard。

Cube 图表与 SQL 图表不同，不写 SQL，而是通过选择维度(dimensions)和指标(indicators)来定义查询。
平台会根据维度和指标自动生成查询逻辑。
"""

from __future__ import annotations

import argparse, json, sys

from _api import (
    api_get, api_post, api_put,
    extract_creator, extract_id,
    parse_json_arg, parse_tags, print_error, print_result,
)


# ========== 元数据查询 ==========

def list_dimensions(dashboard_id="") -> dict:
    """获取平台可用维度列表。"""
    params = {"dashboardId": dashboard_id} if dashboard_id else {}
    data = api_get("/dashboard-query/dimensions", params=params).get("data", [])
    slim = []
    for d in (data if isinstance(data, list) else []):
        item = {
            "id": d.get("id", ""),
            "alias": d.get("alias", ""),
            "name": d.get("name", ""),
            "type": d.get("type", ""),
            "dataType": d.get("dataType", ""),
        }
        if d.get("games"):
            item["games"] = d["games"]
        if d.get("providerType"):
            item["providerType"] = d["providerType"]
        slim.append(item)
    return {"count": len(slim), "dimensions": slim}


def list_indicators(dashboard_id="") -> dict:
    """获取平台可用指标列表。优先走 charts 路径（dashboard 路径可能返回空）。"""
    params = {"dashboardId": dashboard_id} if dashboard_id else {}
    data = api_get("/charts/indicators", params=params).get("data", [])
    slim = []
    for ind in (data if isinstance(data, list) else []):
        item = {
            "id": ind.get("id", ""),
            "alias": ind.get("alias", ""),
            "name": ind.get("name", ""),
            "dataType": ind.get("dataType", ""),
            "format": ind.get("format", ""),
        }
        if ind.get("cohort"):
            item["cohort"] = True
        if ind.get("games"):
            item["games"] = ind["games"]
        if ind.get("groupId"):
            item["groupId"] = ind["groupId"]
        slim.append(item)
    return {"count": len(slim), "indicators": slim}


def query_dimension_values(dimension_id="", alias="", dashboard_id="", wheres=None) -> dict:
    """查询维度的可选值列表。支持按 ID 或 alias 查询。"""
    body = {"wheres": wheres or []}
    params = {"dashboardId": dashboard_id} if dashboard_id else {}
    if alias:
        data = api_post(f"/dashboard-query/alias/{alias}", body=body, params=params).get("data", [])
    elif dimension_id:
        data = api_post(f"/dashboard-query/dimension/{dimension_id}", body=body, params=params).get("data", [])
    else:
        raise ValueError("需要提供 dimension_id 或 alias")
    values = []
    for v in (data if isinstance(data, list) else []):
        values.append({"name": v.get("name", ""), "value": v.get("value", "")})
    return {"count": len(values), "values": values}


def get_chart_need_data(chart_id: str, chart_type="CUBE", dashboard_id="") -> dict:
    """获取图表所需的维度与指标。"""
    params = {"chartsId": chart_id, "type": chart_type}
    if dashboard_id:
        params["dashboardId"] = dashboard_id
    data = api_get("/dashboard-query/chart/need/data", params=params).get("data", {})
    return {
        "chartId": chart_id,
        "useDimensions": data.get("useDimensions", []),
        "useIndicators": data.get("useIndicators", []),
    }


# ========== Cube 图表 CRUD ==========

def create_cube_chart(name: str, dimensions: list, indicators: list,
                      tags=None, description="") -> dict:
    """创建 Cube 图表。

    Args:
        dimensions: 维度 ID 列表，如 ["60d0270962a4005e8b481e1f"]
        indicators: 指标配置列表，如 [{"id": "xxx", "alias": "dau"}]
    """
    # 创建图表壳
    body = {"name": name, "type": "CUBE"}
    if tags:
        body["customTags"] = tags
    if description:
        body["description"] = description
    result = api_post("/charts", body=body)
    chart_id = extract_id(result.get("data", ""))
    if not chart_id:
        raise RuntimeError("Cube 图表创建失败，API 未返回 ID")

    info = {"chartId": chart_id, "name": name, "type": "CUBE",
            "message": f"Cube 图表 '{name}' 创建成功！"}

    # 如果提供了维度和指标，通过 example/query 验证配置
    if dimensions or indicators:
        info["dimensions"] = dimensions
        info["indicators"] = indicators

    return info


def get_cube_detail(chart_id: str, from_dashboard_id="") -> dict:
    """获取 Cube 图表详情。"""
    params = {"fromDashboardId": from_dashboard_id} if from_dashboard_id else {}
    result = api_get(f"/charts/detail/{chart_id}", params=params)
    data = result.get("data", result)

    info = {k: data.get(k, "") for k in ("id", "name", "description", "type",
                                           "createdAt", "updatedAt")}
    info["id"] = info["id"] or chart_id
    info["customTags"] = data.get("customTags")
    info["permission"] = data.get("permission", 0)
    info["dimensions"] = data.get("dimensions", [])
    info["indicators"] = data.get("indicators", [])
    info["wheres"] = data.get("wheres", [])
    info["havingList"] = data.get("havingList", [])
    info["tagFilters"] = data.get("tagFilters", [])
    info["otherFilters"] = data.get("otherFilters", [])
    info["arguments"] = data.get("arguments", [])
    info["argumentDependencies"] = data.get("argumentDependencies", [])

    slim_viz = []
    for v in data.get("visualizations", []):
        sv = {"id": v.get("id", ""), "name": v.get("name", ""), "type": v.get("type", "")}
        opts = v.get("options") or {}
        sv["options"] = {k: opts[k] for k in opts if opts[k] is not None}
        slim_viz.append(sv)
    info["visualizations"] = slim_viz

    info.update(extract_creator(data))
    return info


def query_cube_chart(chart_id: str, dashboard_id="", arguments=None,
                     use_cache=True, max_rows=1000) -> dict:
    """查询 Cube 图表数据。"""
    body = {"arguments": arguments or []}
    if dashboard_id:
        data = api_post(f"/dashboard-query/charts/{chart_id}", body=body,
                        params={"dashboardId": dashboard_id, "isCache": use_cache}).get("data", {})
    else:
        data = api_post(f"/charts/query/{chart_id}", body=body).get("data", {})

    if not isinstance(data, dict):
        return {"error": "unexpected format", "raw": data}
    columns = data.get("columns", data.get("header", []))
    all_rows = data.get("result", data.get("rows", data.get("data", [])))
    if not isinstance(all_rows, list):
        all_rows = []
    rows = all_rows[:max_rows]
    return {"columns": columns, "rows": rows, "totalRows": len(all_rows),
            "returnedRows": len(rows)}


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(description="Cube 图表操作")
    sub = parser.add_subparsers(dest="action")

    # 元数据
    p = sub.add_parser("dimensions", help="获取平台可用维度列表")
    p.add_argument("--dashboard", default="")
    p.add_argument("--filter", default="", help="按名称/alias 过滤")

    p = sub.add_parser("indicators", help="获取平台可用指标列表")
    p.add_argument("--dashboard", default="")
    p.add_argument("--filter", default="", help="按名称/alias 过滤")

    p = sub.add_parser("dim-values", help="查询维度可选值")
    p.add_argument("--id", default="", dest="dim_id", help="维度 ID")
    p.add_argument("--alias", default="", help="维度别名（如 game_cd）")
    p.add_argument("--dashboard", default="")
    p.add_argument("--wheres", default="", help="过滤条件 JSON")

    p = sub.add_parser("need-data", help="获取图表所需维度与指标")
    p.add_argument("chart_id")
    p.add_argument("--dashboard", default="")

    # CRUD
    p = sub.add_parser("create", help="创建 Cube 图表")
    p.add_argument("--name", required=True)
    p.add_argument("--dimensions", default="", help="维度 ID 列表，逗号分隔")
    p.add_argument("--indicators", default="", help="指标配置 JSON 数组")
    p.add_argument("--tags", default="")
    p.add_argument("--description", default="")

    p = sub.add_parser("detail", help="获取 Cube 图表详情")
    p.add_argument("chart_id")
    p.add_argument("--from-dashboard", default="")

    p = sub.add_parser("query", help="查询 Cube 图表数据")
    p.add_argument("chart_id")
    p.add_argument("--dashboard", default="")
    p.add_argument("--args", default="{}")
    p.add_argument("--no-cache", dest="use_cache", action="store_false")
    p.add_argument("--max-rows", type=int, default=1000)

    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        sys.exit(1)

    try:
        if args.action == "dimensions":
            result = list_dimensions(dashboard_id=args.dashboard)
            if args.filter:
                kw = args.filter.lower()
                result["dimensions"] = [d for d in result["dimensions"]
                                        if kw in d.get("name", "").lower()
                                        or kw in d.get("alias", "").lower()]
                result["count"] = len(result["dimensions"])

        elif args.action == "indicators":
            result = list_indicators(dashboard_id=args.dashboard)
            if args.filter:
                kw = args.filter.lower()
                result["indicators"] = [i for i in result["indicators"]
                                        if kw in i.get("name", "").lower()
                                        or kw in i.get("alias", "").lower()]
                result["count"] = len(result["indicators"])

        elif args.action == "dim-values":
            wheres = parse_json_arg(args.wheres) if args.wheres else None
            result = query_dimension_values(dimension_id=args.dim_id, alias=args.alias,
                                            dashboard_id=args.dashboard, wheres=wheres)

        elif args.action == "need-data":
            result = get_chart_need_data(chart_id=args.chart_id, dashboard_id=args.dashboard)

        elif args.action == "create":
            dims = [d.strip() for d in args.dimensions.split(",") if d.strip()] if args.dimensions else []
            inds = parse_json_arg(args.indicators) if args.indicators else []
            result = create_cube_chart(name=args.name, dimensions=dims, indicators=inds,
                                       tags=parse_tags(args.tags), description=args.description)

        elif args.action == "detail":
            result = get_cube_detail(chart_id=args.chart_id, from_dashboard_id=args.from_dashboard)

        elif args.action == "query":
            ad = parse_json_arg(args.args)
            arguments = [{"keyword": k, "values": v if isinstance(v, list) else [str(v)]}
                         for k, v in ad.items()] if ad else []
            result = query_cube_chart(chart_id=args.chart_id, dashboard_id=args.dashboard,
                                      arguments=arguments, use_cache=args.use_cache,
                                      max_rows=args.max_rows)

        else:
            parser.print_help()
            sys.exit(1)

        print_result(result)
    except json.JSONDecodeError as e:
        print_error(f"JSON 解析失败: {e}"); sys.exit(1)
    except Exception as e:
        print_error(str(e)); sys.exit(1)


if __name__ == "__main__":
    main()
