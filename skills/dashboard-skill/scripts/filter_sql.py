#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Filter SQL 管理：管理 Dashboard 筛选器的动态选项 SQL。"""

from __future__ import annotations

import argparse, json, sys
from _api import api_get, api_post, api_put, extract_id, print_error, print_result, resolve_datasource


def list_filter_sqls(name="") -> dict:
    params = {"name": name} if name else {}
    raw = api_get("/filter-sql/self", params=params).get("data", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    slim = [{"id": f.get("id", ""), "name": f.get("name", ""), "datasource": f.get("datasource", "")}
            for f in raw]
    return {"filterSqls": slim}


def get_filter_sql(filter_sql_id: str) -> dict:
    data = api_get(f"/filter-sql/id/{filter_sql_id}").get("data", {})
    return {k: data.get(k, "") for k in ("id", "name", "sql", "datasource")}


def create_filter_sql(name: str, sql: str, datasource_type="TRINO", db="hive") -> dict:
    result = api_post("/filter-sql", body={
        "name": name, "sql": sql, "datasource": resolve_datasource(datasource_type), "db": db
    })
    fid = extract_id(result.get("data", ""))
    return {"filterSqlId": fid, "name": name, "message": f"Filter SQL '{name}' 创建成功！"}


def update_filter_sql(filter_sql_id: str, name=None, sql=None, datasource_type=None, db=None) -> dict:
    existing = api_get(f"/filter-sql/id/{filter_sql_id}").get("data", {})
    body = {
        "name": name if name is not None else existing.get("name", ""),
        "sql": sql if sql is not None else existing.get("sql", ""),
        "datasource": resolve_datasource(datasource_type) if datasource_type is not None else existing.get("datasource", "TRINO"),
        "db": db if db is not None else existing.get("db", "hive"),
    }
    api_put(f"/filter-sql/{filter_sql_id}", body=body)
    return {"filterSqlId": filter_sql_id, "message": "Filter SQL 更新成功！"}


def execute_filter_sql(filter_sql_id: str) -> dict:
    return {"filterSqlId": filter_sql_id,
            "result": api_post(f"/filter-sql/execute/id/{filter_sql_id}").get("data", {})}


def test_filter_sql(sql: str, datasource_type="TRINO") -> dict:
    """保存前测试 Filter SQL（不创建，仅执行验证）。"""
    ds = resolve_datasource(datasource_type)
    result = api_post("/filter-sql/execute/example", body=sql,
                      params={"datasource": ds}, timeout=60)
    return {"datasource": ds, "result": result.get("data", [])}


def batch_update_filter_datasource(filter_ids: list, to_datasource: str) -> dict:
    """批量更新 Filter SQL 数据源。"""
    ds = resolve_datasource(to_datasource)
    api_post("/filter-sql/datasource/batch-update", body={"ids": filter_ids, "toDatasource": ds})
    return {"filterIds": filter_ids, "toDatasource": ds,
            "message": f"已将 {len(filter_ids)} 个 Filter SQL 数据源更新为 {ds}"}


def main():
    parser = argparse.ArgumentParser(description="Filter SQL 管理")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("list"); p.add_argument("--name", default="")
    p = sub.add_parser("get"); p.add_argument("filter_sql_id")
    p = sub.add_parser("create"); p.add_argument("--name", required=True); p.add_argument("--sql", required=True); p.add_argument("--datasource", default="TRINO"); p.add_argument("--db", default="hive")
    p = sub.add_parser("execute"); p.add_argument("filter_sql_id")
    p = sub.add_parser("update"); p.add_argument("filter_sql_id"); p.add_argument("--name", default=None); p.add_argument("--sql", default=None); p.add_argument("--datasource", default=None); p.add_argument("--db", default=None)
    p = sub.add_parser("test", help="保存前测试 Filter SQL"); p.add_argument("--sql", required=True); p.add_argument("--datasource", default="TRINO")
    p = sub.add_parser("batch-update-ds", help="批量更新 Filter SQL 数据源"); p.add_argument("filter_ids", nargs="+"); p.add_argument("--datasource", required=True)

    args = parser.parse_args()
    if not args.action:
        parser.print_help(); sys.exit(1)

    try:
        if args.action == "list": result = list_filter_sqls(name=args.name)
        elif args.action == "get": result = get_filter_sql(args.filter_sql_id)
        elif args.action == "create": result = create_filter_sql(name=args.name, sql=args.sql, datasource_type=args.datasource, db=args.db)
        elif args.action == "execute": result = execute_filter_sql(args.filter_sql_id)
        elif args.action == "update": result = update_filter_sql(filter_sql_id=args.filter_sql_id, name=args.name, sql=args.sql, datasource_type=args.datasource, db=args.db)
        elif args.action == "test": result = test_filter_sql(sql=args.sql, datasource_type=args.datasource)
        elif args.action == "batch-update-ds": result = batch_update_filter_datasource(filter_ids=args.filter_ids, to_datasource=args.datasource)
        else: parser.print_help(); sys.exit(1)
        print_result(result)
    except Exception as e:
        print_error(str(e)); sys.exit(1)


if __name__ == "__main__":
    main()
