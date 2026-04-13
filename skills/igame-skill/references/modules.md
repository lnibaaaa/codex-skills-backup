# iGame Skill — 模块与接口参考

## 游戏 ID

| 游戏 | ID |
|------|----|
| P2 (Age of Apes) | 1041 |
| BA (Brutal Age) | 1012 |
| KOW (Kiss of War) | 1038 |
| X1 (Raft War) | 1088 |
| X2 (Shop & Goblins) | 1089 |
| X3 (TavernLegend) | 1090 |
| X9 | 1108 |

切换游戏：修改 `~/.igame-auth.json` 的 `gameId`。

---

## 常用接口速查

| 需求 | 接口路径 | 方法 |
|------|---------|------|
| 查服务器列表 | `serverMgr/serverList/getServerList` | read |
| 改导量权重 | `serverMgr/serverList/setServerRate` | write |
| 停止导量 | `serverMgr/index/stop` | write |
| 补量 | `serverMgr/index/restart` | write |
| 备服 | `serverMgr/readyServer/readyServer` | write |
| 查审核服 | `serverMgr/auditServer/getAuditServerList` | read |
| 更新审核服版本 | `serverMgr/auditServer/updateAuditServer` | write |
| 挂维护 | `serverMgr/serverList/flowMaintain` | write |
| 解维护 | `serverMgr/serverList/flowMaintainLift` | write |
| 修改导量规则 | `serverMgr/index/editFlowRule` | write |
| 查玩家 | `player/playerSearch/...`（先 ls player 确认子模块） | read |
| 发邮件 | `email/...`（先 ls email 确认子模块） | write |

---

## 全模块列表（32个）

| 模块 | 接口数 | 功能 |
|------|--------|------|
| serverMgr | 74 | 服务器导量、合服、热更、维护、审核服 |
| customer | 262 | 客服系统（工单/聊天） |
| email | 89 | 邮件发送与管理 |
| playerDetails | 71 | 玩家详情（订单/道具/行为） |
| admin | 80 | 管理员操作 |
| activity | 53 | 活动管理（创建/兑换码） |
| playerManage | 31 | 玩家管理（封号/解封/白名单） |
| questionnaire | 32 | 问卷调查 |
| infoSearch | 32 | 信息检索 |
| toolbox | 39 | GM 工具箱 |
| internal_welfare | 46 | 内部福利 |
| _common | 47 | 公共接口 |
| applyInternalWelfare | 24 | 申请内部福利 |
| collectHistory | 12 | 收集历史 |
| out_email | 23 | 对外邮件 |
| player | 24 | 玩家基础查询 |
| maintenance | 26 | 维护管理 |
| configuration | 17 | 配置管理 |
| store_mgr | 15 | 商店管理 |
| MODS | 14 | MOD管理 |
| dingdingNotify | 15 | 钉钉通知 |
| competenceMng | 8 | 权限管理 |
| league | 12 | 联盟/公会 |
| notification | 7 | 通知 |
| approval | 2 | 审批 |
| batch_handle | 11 | 批量处理 |
| operationLog | 4 | 操作日志 |
| menu | 2 | 菜单 |
| user | 8 | 用户 |
| userMng | 2 | 用户管理 |
| domain | 2 | 域名 |
| aiAudit | 6 | AI 审核 |
