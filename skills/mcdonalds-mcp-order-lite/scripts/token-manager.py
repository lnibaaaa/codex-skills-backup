#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
McDonald's MCP Token Manager
管理多个 MCP Token，支持添加、切换、删除

Token 存储在 ~/.mcd-tokens.json
"""

import json
import os
import sys
from pathlib import Path

TOKEN_FILE = Path.home() / ".mcd-tokens.json"


def load_tokens() -> dict:
    """加载已保存的 tokens"""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"tokens": {}, "current": None}


def save_tokens(data: dict):
    """保存 tokens"""
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 设置文件权限为仅用户可读写
    os.chmod(TOKEN_FILE, 0o600)


def add_token(name: str, token: str):
    """添加新 token"""
    data = load_tokens()
    data["tokens"][name] = token
    # 如果是第一个 token，自动设为当前
    if data["current"] is None:
        data["current"] = name
    save_tokens(data)
    print(f"✅ Token '{name}' 已添加")
    if data["current"] == name:
        print(f"   已设为当前使用的 Token")


def remove_token(name: str):
    """删除 token"""
    data = load_tokens()
    if name not in data["tokens"]:
        print(f"❌ Token '{name}' 不存在")
        return
    del data["tokens"][name]
    # 如果删除的是当前 token，切换到另一个
    if data["current"] == name:
        if data["tokens"]:
            data["current"] = list(data["tokens"].keys())[0]
            print(f"   已切换到 '{data['current']}'")
        else:
            data["current"] = None
    save_tokens(data)
    print(f"✅ Token '{name}' 已删除")


def switch_token(name: str):
    """切换当前 token"""
    data = load_tokens()
    if name not in data["tokens"]:
        print(f"❌ Token '{name}' 不存在")
        print(f"   可用: {', '.join(data['tokens'].keys()) or '无'}")
        return
    data["current"] = name
    save_tokens(data)
    print(f"✅ 已切换到 Token '{name}'")


def list_tokens():
    """列出所有 tokens"""
    data = load_tokens()
    if not data["tokens"]:
        print("📭 暂无保存的 Token")
        print("\n获取 Token:")
        print("  1. 访问 https://open.mcd.cn/mcp")
        print("  2. 登录 → 控制台 → 激活")
        print("\n添加 Token:")
        print("  python token-manager.py add <名称> <token>")
        return

    print("🎫 已保存的 Token:")
    print("-" * 40)
    for name, token in data["tokens"].items():
        current = " ← 当前" if name == data["current"] else ""
        # 只显示 token 的前8位和后4位
        masked = token[:8] + "..." + token[-4:] if len(token) > 12 else token
        print(f"  {name}: {masked}{current}")
    print("-" * 40)
    print(f"共 {len(data['tokens'])} 个 Token")


def get_current_token() -> tuple:
    """获取当前 token，返回 (name, token)"""
    data = load_tokens()
    if not data["current"] or data["current"] not in data["tokens"]:
        return None, None
    return data["current"], data["tokens"][data["current"]]


def interactive_add():
    """交互式添加 token"""
    print("📝 添加新的 MCP Token")
    print("-" * 40)
    print("如果还没有 Token，请先获取:")
    print("  1. 访问 https://open.mcd.cn/mcp")
    print("  2. 点击登录，使用手机号验证")
    print("  3. 点击控制台 → 激活")
    print("-" * 40)

    name = input("请输入名称 (如 'personal', 'work'): ").strip()
    if not name:
        print("❌ 名称不能为空")
        return

    token = input("请粘贴 Token: ").strip()
    if not token:
        print("❌ Token 不能为空")
        return

    add_token(name, token)


def main():
    if len(sys.argv) < 2:
        # 无参数时显示列表
        list_tokens()
        return

    cmd = sys.argv[1].lower()

    if cmd == "list" or cmd == "ls":
        list_tokens()

    elif cmd == "add":
        if len(sys.argv) >= 4:
            add_token(sys.argv[2], sys.argv[3])
        else:
            interactive_add()

    elif cmd == "remove" or cmd == "rm" or cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: python token-manager.py remove <name>")
            return
        remove_token(sys.argv[2])

    elif cmd == "switch" or cmd == "use":
        if len(sys.argv) < 3:
            print("Usage: python token-manager.py switch <name>")
            return
        switch_token(sys.argv[2])

    elif cmd == "current":
        name, token = get_current_token()
        if name:
            masked = token[:8] + "..." + token[-4:] if len(token) > 12 else token
            print(f"当前: {name} ({masked})")
        else:
            print("❌ 未设置当前 Token")

    elif cmd == "export":
        # 导出当前 token 到环境变量格式
        name, token = get_current_token()
        if token:
            print(f"export MCD_MCP_TOKEN={token}")
        else:
            print("# No token configured", file=sys.stderr)

    elif cmd == "help" or cmd == "-h" or cmd == "--help":
        print("McDonald's MCP Token Manager")
        print("=" * 40)
        print("\nCommands:")
        print("  list              列出所有 token")
        print("  add [name] [token]  添加新 token")
        print("  remove <name>     删除 token")
        print("  switch <name>     切换当前 token")
        print("  current           显示当前 token")
        print("  export            导出为环境变量格式")
        print("\nExamples:")
        print("  python token-manager.py add personal abc123...")
        print("  python token-manager.py switch work")
        print("  eval $(python token-manager.py export)")

    else:
        print(f"Unknown command: {cmd}")
        print("Run 'python token-manager.py help' for usage")


if __name__ == "__main__":
    main()
