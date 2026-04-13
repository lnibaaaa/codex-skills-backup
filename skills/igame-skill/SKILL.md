---
name: igame-skill
description: 操作 iGame 游戏运营支撑平台，覆盖 32 个模块、1090 个接口。支持服务器导量管理、玩家查询/封号、邮件发送、活动管理、合服、热更、维护挂起、GM 操作等全部运营功能。支持 P2/BA/KOW/X1/X2/X9 全游戏。触发条件：(1) 提到"服务器"、"导量"、"开服"、"停服"、"补量"、"备服"、"合服"、"热更"、"维护"、"审核服"，(2) 提到"玩家"+"封号/解封/查询/订单"，(3) 提到"发邮件"、"GM 操作"、"工具箱"，(4) 提到 P2/X2/X9/KOW/BA + 任意运营操作，(5) 需要查询或操作 iGame 平台任何功能。
---

# iGame Skill

认证文件：`~/.igame-auth.json`。首次使用或 token 过期（约 10 天）运行：

```bash
bash ./scripts/setup-auth.sh
```

切换游戏：修改 `~/.igame-auth.json` 的 `gameId`（P2=1041, X2=1089, X9=1108 等，详见 [references/modules.md](references/modules.md)）。

## 工作流

**Step 1 — 定位接口**

```bash
node ./scripts/igame-query.js ls ""                          # 列出 32 个模块
node ./scripts/igame-query.js ls "serverMgr"                 # 展开某模块
node ./scripts/igame-query.js describe "serverMgr/serverList/getServerList"  # 查参数
```

不确定模块名时先 `ls ""`，再逐级展开。常用接口速查见 [references/modules.md](references/modules.md)。

**Step 2 — 查询**

```bash
node ./scripts/igame-query.js read "<module/sub/api>" '<json params>'
```

**Step 3 — 操作（执行前必须向用户确认）**

```bash
node ./scripts/igame-query.js write "<module/sub/api>" '<json params>'
```

## ⚠️ 接口易混淆警告

| 操作 | 正确接口 | 错误接口（勿用）|
|------|---------|--------------|
| 改权重 | `serverMgr/serverList/setServerRate` `{"id":xxx,"serverRate":400}` | ~~`serverMgr/index/editFlowRule`~~ — 改的是导量规则，返回 success 但**权重不变** |
| 修改导量规则（国家/语言/平台） | `serverMgr/index/editFlowRule` | — |

## ⚠️ Gotchas

**1. `--game` 参数临时切换游戏，无需改 auth 文件**
操作不同游戏时用 `--game p2|x2|x9|x3` 临时覆盖 gameId，`~/.igame-auth.json` 文件不动：
```bash
node ./scripts/igame-query.js --game x2 read "serverMgr/serverList/getServerList" '{"pageIndex":1,"pageSize":20,"status":5}'
```
gameId 映射：P2=1041, X2=1089, X9=1108, X1=1088, X3=1090。

**2. P2 导量双线并行，260x 渠道服不纳入主线操作**
P2 同时维护两条线：国际服（209xxxx 段）+ 中文服（260xxxx 段开头但主线是 209xxxx 附近的服）。
260x 开头的是独立渠道服，**不参与主线导量权重操作**。改权重只动主线服，不改 260x。
X2 只有一条线（106xxxx 段）。

**3. 导量指令默认意图**
"切导量到最新服" = 最新服 rate 100→400，前一服 rate 400→300（与其他服对齐）。
不是只改最新服，同时要把前一服降下来。

**4. `editFlowRule` 返回 `success:true` 是假阳性**
改权重误用 `editFlowRule` 时，接口会返回成功但权重实际不变。改完后必须用 `getServerList` 验证 `serverRate` 字段确认生效。

## getServerList 响应字段速查

`getServerList` 必填参数：`pageIndex`（缺少会报 500）。推荐用 `pageSize:200` 一次拉全量。

| 字段 | 含义 | 备注 |
|------|------|------|
| `id` | 内部 ID | `setServerRate` 的 `id` 参数用这个，不是 `gameServerId` |
| `gameServerId` | 游戏服 ID | X2 格式：`100NNXX`，NN=服序号，XX=02。例：1007302 = 73服 |
| `gameServerName` | 服名 | 英文名，如 Lodecore |
| `flowRate` | 当前权重 | 查询时看这个字段（不是 `rate` 或 `serverRate`） |
| `status` | 状态 | 5=正常导量中 |

**X2 服序号解码**：`gameServerId` 中间两位即服序号。`1007302` → 73服，`1007202` → 72服。

**标准导量切服流程（X2）**：
```bash
# 1. 查当前状态（pageIndex 必填）
node ./scripts/igame-query.js --game x2 read "serverMgr/serverList/getServerList" '{"pageIndex":1,"pageSize":200}' \
  | python3 -c "import json,sys; s=json.load(sys.stdin)['data']; [print(x['id'],x['gameServerId'],x['gameServerName'],x['flowRate']) for x in s if (x.get('flowRate') or 0)>0]"

# 2. 新服 100→400，前服 400→300（id 从上一步拿）
node ./scripts/igame-query.js --game x2 write "serverMgr/serverList/setServerRate" '{"id":2956,"serverRate":400}'
node ./scripts/igame-query.js --game x2 write "serverMgr/serverList/setServerRate" '{"id":2950,"serverRate":300}'
```

## 示例

```bash
# 查 P2 导量中的服务器
node ./scripts/igame-query.js read "serverMgr/serverList/getServerList" '{"pageIndex":1,"pageSize":20,"status":5}'

# 改权重（确认后执行）
node ./scripts/igame-query.js write "serverMgr/serverList/setServerRate" '{"id":"2608702","serverRate":400}'
```
