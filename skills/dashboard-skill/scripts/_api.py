#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公共基础设施：配置加载、API 客户端、工具函数。"""

from __future__ import annotations

import ast, json, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests

# ========== 配置加载 ==========
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard_skill_config.json")

def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[config] 加载失败: {e}", file=sys.stderr)
        return {}

_CONFIG = _load_config()

# ========== 常量 ==========
_TASK_TERMINAL_SUCCESS = frozenset({"COMPLETED", "SUCCESS", "FINISHED", 2, "2"})
_TASK_TERMINAL_FAILURE = frozenset({"FAILED", "ERROR", "CANCELLED", 3, "3", 4, "4"})
_RETRY_BASE_DELAY = 0.5
_RETRY_BACKOFF_FACTOR = 2
_POLL_BACKOFF_FACTOR = 1.5
_POLL_MAX_INTERVAL = 3.0
DEFAULT_MAX_ROWS = 1000


class TaskExpiredError(RuntimeError):
    """后端异步任务已过期（code=10009），需重新提交。"""
    pass

# ========== 配置派生（仅 API 地址和 Web URL 从 config 读取） ==========
PUBLIC_API_HOST = _CONFIG.get("api", {}).get("public_api_host", "https://datain-api.tap4fun.com")
PUBLIC_API_PREFIX = _CONFIG.get("api", {}).get("public_api_prefix", "/public_api")
DEFAULT_TIMEOUT = _CONFIG.get("api", {}).get("default_timeout", 30)

DATASOURCE_TYPES = ["TRINO", "TRINO_CN", "A3_TRINO"]

# 数据源别名映射：用户/平台展示名 → API 内部名
_DATASOURCE_ALIASES = {
    "TRINO_AWS": "TRINO", "TRINO AWS": "TRINO",
    "TRINO_HF": "A3_TRINO", "TRINO A3": "A3_TRINO",
}


def resolve_datasource(name: str) -> str:
    """将数据源名称统一为 API 内部名（支持别名）。"""
    upper = name.strip().upper()
    return _DATASOURCE_ALIASES.get(upper, upper)

CHART_SUB_TYPES = frozenset({"LINE", "BAR", "PIE", "AREA", "SCATTER", "FUNNEL", "HEATMAP", "BOXPLOT"})

DASHBOARD_WEB_URL = _CONFIG.get("web_urls", {}).get("dashboard", "https://datain.tap4fun.com/dashboard")

# ========== API Key ==========
_API_KEY_CACHE: Optional[str] = None

def get_api_key() -> str:
    global _API_KEY_CACHE
    if _API_KEY_CACHE is not None:
        return _API_KEY_CACHE
    api_key = os.getenv("DATAIN_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({
            "error": "API_KEY_NOT_CONFIGURED",
            "message": "DATAIN_API_KEY 环境变量未设置！",
            "solution": "export DATAIN_API_KEY=你的APIKey\n获取: https://datain.tap4fun.com/ → 个人中心 → 设置 → APP KEY",
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    _API_KEY_CACHE = api_key
    return _API_KEY_CACHE

# ========== Session 连接池（线程安全） ==========
_thread_local = threading.local()

def _get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=1)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _thread_local.session = s
    return s

# ========== 核心 API 请求 ==========
def api_request(method: str, path: str, params: Optional[Dict] = None,
                body: Optional[Any] = None, timeout: Optional[int] = None,
                max_retries: int = 2) -> Dict[str, Any]:
    """发送 Public API 请求，自动追加 api_key，含重试。"""
    url = f"{PUBLIC_API_HOST}{PUBLIC_API_PREFIX}{path}"
    session = _get_session()
    params = dict(params or {})
    params["api_key"] = get_api_key()
    timeout = timeout or DEFAULT_TIMEOUT

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = session.request(method=method.upper(), url=url, params=params,
                                   json=body if body is not None else None, timeout=timeout)
            if resp.status_code >= 500 and attempt < max_retries:
                time.sleep(_RETRY_BASE_DELAY * (_RETRY_BACKOFF_FACTOR ** attempt))
                continue
            if resp.status_code == 401:
                raise RuntimeError("认证失败 (401)，请检查 DATAIN_API_KEY")
            if resp.status_code >= 400:
                raise RuntimeError(f"API 错误 ({resp.status_code}): {method} {path} - {resp.text[:300]}")
            try:
                data = resp.json()
            except Exception:
                return {"raw_text": resp.text}
            if isinstance(data, dict) and data.get("success") is False:
                msg = data.get("message", "未知业务错误")
                raise RuntimeError(f"API 业务错误 (code={data.get('code', '')}): {method} {path} - {msg}")
            return data
        except requests.exceptions.Timeout:
            last_error = RuntimeError(f"API 超时 ({timeout}s): {method} {path}")
        except requests.exceptions.ConnectionError as e:
            last_error = RuntimeError(f"API 连接失败: {method} {path} - {e}")
        if attempt < max_retries:
            time.sleep(_RETRY_BASE_DELAY * (_RETRY_BACKOFF_FACTOR ** attempt))
    raise last_error

def api_get(path, params=None, **kw):
    return api_request("GET", path, params=params, **kw)

def api_post(path, body=None, params=None, **kw):
    return api_request("POST", path, params=params, body=body, **kw)

def api_put(path, body=None, params=None, **kw):
    return api_request("PUT", path, params=params, body=body, **kw)

def api_delete(path, body=None, params=None, **kw):
    return api_request("DELETE", path, params=params, body=body, **kw)

# ========== 并发批量请求 ==========
def api_batch(calls: List[Tuple], max_workers: int = 6, timeout: Optional[int] = None) -> List[Dict]:
    """并发执行 API 请求。calls: [(method, path, params, body), ...]"""
    results = [None] * len(calls)
    def _do(idx, m, p, par, bod):
        try:
            return idx, api_request(m, p, params=par, body=bod, timeout=timeout)
        except Exception as e:
            return idx, {"error": str(e), "path": p}

    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls))) as pool:
        futures = []
        for i, c in enumerate(calls):
            futures.append(pool.submit(_do, i, c[0], c[1],
                                       c[2] if len(c) > 2 else None,
                                       c[3] if len(c) > 3 else None))
        for f in as_completed(futures):
            idx, result = f.result()
            results[idx] = result
    return results

def api_batch_get(paths: List[str], max_workers: int = 6) -> List[Dict]:
    return api_batch([("GET", p, None, None) for p in paths], max_workers=max_workers)

# ========== 异步任务轮询 ==========
def _poll_task(task_id: str, api_path: str, error_prefix: str,
               api_params: Optional[Dict] = None, max_wait: float = 300.0) -> Dict:
    """通用异步任务轮询（指数退避）。"""
    start, interval = time.time(), _RETRY_BASE_DELAY
    url = api_path.format(task_id=task_id)
    while True:
        if time.time() - start > max_wait:
            raise RuntimeError(f"{error_prefix}超时 ({max_wait}s): {task_id}")
        try:
            result = api_get(url, params=api_params)
        except RuntimeError as e:
            if "10009" in str(e):
                raise TaskExpiredError(f"{error_prefix}已过期: {task_id}") from e
            raise
        data = result.get("data", {})
        if not isinstance(data, dict):
            if data:
                return data if isinstance(data, dict) else {"raw": data}
            time.sleep(interval)
            interval = min(interval * _POLL_BACKOFF_FACTOR, _POLL_MAX_INTERVAL)
            continue
        status = data.get("status", "")
        if status in _TASK_TERMINAL_SUCCESS:
            return data
        if status in _TASK_TERMINAL_FAILURE:
            raise RuntimeError(f"{error_prefix}失败: {data.get('errorMessage', data.get('message', '未知'))}")
        time.sleep(interval)
        interval = min(interval * _POLL_BACKOFF_FACTOR, _POLL_MAX_INTERVAL)

def poll_async_task(task_id: str, **kw) -> Dict:
    return _poll_task(task_id, "/dashboard-query/task/{task_id}", "异步任务",
                      api_params={"isCache": False, "type": "SQL"}, **kw)

def poll_chart_task(task_id: str, **kw) -> Dict:
    return _poll_task(task_id, "/charts/task/{task_id}", "图表查询任务",
                      api_params={"isCache": False, "type": "SQL"}, **kw)

def poll_async_tasks_batch(task_ids: List[str], max_workers: int = 6,
                           max_wait: float = 300.0, poll_fn=None) -> Dict[str, Dict]:
    """并发轮询多个异步任务。"""
    if not task_ids:
        return {}
    poll_fn = poll_fn or poll_async_task
    results = {}
    def _poll(tid):
        try:
            return tid, poll_fn(tid, max_wait=max_wait)
        except TaskExpiredError:
            return tid, {"expired": True, "error": "任务已过期，需重新提交"}
        except Exception as e:
            return tid, {"error": str(e)}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(task_ids))) as pool:
        for f in as_completed([pool.submit(_poll, t) for t in task_ids]):
            tid, data = f.result()
            results[tid] = data
    return results

# ========== 工具函数 ==========
def print_result(data: Any, compact: bool = False) -> None:
    if compact:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))

def print_error(message: str) -> None:
    print(json.dumps({"error": True, "message": message}, ensure_ascii=False, indent=2))

def parse_json_arg(s: str) -> Any:
    """解析 CLI 传入的 JSON 字符串，兼容 AI agent 常见的单引号写法。"""
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(s)
        except Exception:
            raise ValueError(f"无法解析为 JSON: {s[:200]}")

def extract_id(data: Any) -> str:
    """从 API 响应的 data 字段中提取 ID（兼容 str / dict / 其他类型）。"""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        return str(data.get("id", "")).strip()
    return str(data).strip() if data else ""

def extract_task_id(data: Any) -> str:
    """从异步任务响应中提取 task ID（优先 taskId，其次 id）。"""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        return str(data.get("taskId", data.get("id", ""))).strip()
    return ""

def extract_creator(data: dict) -> dict:
    """从 API 数据中提取创建者信息。"""
    creator = data.get("creator", {})
    if isinstance(creator, dict):
        return {"creatorName": creator.get("name", ""), "creatorEmail": creator.get("email", "")}
    return {}

def parse_tags(s: str) -> list:
    """逗号分隔的标签字符串 → 列表。"""
    return [t.strip() for t in s.split(",") if t.strip()] if s else []

def extract_sql_variables(sql: str) -> List[str]:
    """从 SQL 中提取 ${variable} 变量名（去重保序）。"""
    seen, result = set(), []
    for m in re.findall(r"\$\{([^}]+)\}", sql or ""):
        m = m.strip()
        if m and m not in seen:
            seen.add(m)
            result.append(m)
    return result

