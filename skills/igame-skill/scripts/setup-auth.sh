#!/bin/bash
set -e

AUTH_FILE="$HOME/.igame-auth.json"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXTRACT_JS="$SKILL_DIR/scripts/extract-auth.js"

echo ""
echo "=== iGame Skill 认证配置 ==="
echo ""
echo "1. 打开 https://igame.tap4fun.com 并登录（企业微信扫码）"
echo ""
echo "2. F12 → Console，粘贴以下代码并回车："
echo ""
echo "   ---"
cat "$EXTRACT_JS" | tr '\n' ' '
echo ""
echo "   ---"
echo ""
echo "   输出的 JSON 里包含 token 和 clientId，复制这两个值。"
echo ""

read -p "Token: " TOKEN
read -p "ClientId: " CLIENT_ID

echo ""
echo "游戏 ID: P2=1041  BA=1012  KOW=1038  X1=1088  X2=1089  X9=1108"
read -p "默认游戏 ID [1041]: " GAME_ID
GAME_ID=${GAME_ID:-1041}

cat > "$AUTH_FILE" << AUTHEOF
{
  "token": "$TOKEN",
  "clientId": "$CLIENT_ID",
  "gameId": "$GAME_ID",
  "regionId": "201"
}
AUTHEOF

echo ""
echo "已写入 $AUTH_FILE"
echo "Token 有效期约 10 天，过期后重新运行此脚本。"
