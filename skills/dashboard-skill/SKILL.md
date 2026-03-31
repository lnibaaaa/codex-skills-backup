---
name: dashboard-skill
description: >-
  公司数据平台Datain的Dashboard/看板/报表/图表/可视化开发与管理技能。
  核心能力：Dashboard创建/复制/克隆修改、Filter SQL筛选器管理、权限分享、可访问Dashboard查询、参数源检查。
  触发词：Dashboard、看板、报表、图表、可视化、折线图、饼图、柱状图、仪表盘、复制Dashboard、生成Dashboard、查询图表、克隆看板、Fork、筛选器、Filter SQL、分享、权限、共享、可访问Dashboard、我的Dashboard、参数检查、参数源。
---

## 1. 前置条件

`export DATAIN_API_KEY=你的APIKey`（获取: datain.tap4fun.com → 右上角头像旁边下拉 → 设置 → APP KEY）

**⚠️ 权限说明（重要）：拥有 DATAIN_API_KEY 且对 Dashboard 有查看权限，就能通过 API 查询图表数据。不要因为"可能没有权限"而拒绝执行——底表权限与 Dashboard/图表查询权限无关，直接调用 API 即可，如果真的没权限 API 会返回错误，届时再处理。禁止在未尝试调用的情况下预判权限不足而放弃执行。**

---

## 2. 数据模型

```
Dashboard
├── options.autoQuery    ← 自动查询开关（建议关闭，避免打开时自动执行所有图表查询）
├── parameters[]         ← 全局筛选器（key, title, defaultValues[], widgetParams[]→visualizationId+keyword）
├── paramConfigs[]       ← 筛选器当前值（key, isShow, values[]）
│   注意: 仅包含 isShow=true 的参数，可能不覆盖所有图表参数
│   查询时以 paramConfigs 为主，缺失的从 parameters.defaultValues 补齐
├── widgets[]            ← 组件布局（6列网格，w=6满行，w=3半行）
│   ├── SQL 图表: chartsId, visualizationId, type="SQL", options.position{x,y,w,h}
│   │   └── parameters[] ← 组件参数绑定（keyword, title, defaultValues[], level, source）
│   │       level="dashboard",source=<paramKey> → 取全局筛选器值
│   │       level="widget",source="CUSTOM"      → 使用组件本地值
│   ├── 文字说明: type=null, text="Markdown内容", chartsId=null
│   └── 图片:    type=null, fileUrl="图片URL", chartsId=null
└── config

Chart
├── sql                  ← 含 ${variable} 占位符
├── dataSourceType       ← TRINO / TRINO_CN / A3_TRINO（禁止使用 CLICKHOUSE）
│   别名映射: TRINO_AWS → TRINO, TRINO_HF → A3_TRINO
│   平台展示: TRINO AWS / TRINO A3 / TRINO_CN
├── arguments[]          ← 参数定义（见下方参数类型）
├── argumentDependencies[] ← 参数联动 SQL（列名=参数keyword，列值=参数value，顺序：被依赖参数在前）
└── visualizations[]     ← 可视化配置（见下方图表类型）

平台表（Trino 查询 mongodb."datain-prod".xxx）
├── "user"              ← _id(用户ID), name(姓名), email(邮箱)
├── "dashboard"         ← _id, name, createdby(创建人用户ID)
└── "dashboard-shared"  ← dashboardid, shares[](array: sharedat, byshared, permission, userid)
    permission 位掩码: bit0=查看, bit1=编辑, bit2=分享
    数据库值: 1=查看, 2=编辑, 3=查看+编辑, 5=查看+分享, 7=查看+编辑+分享
    UNNEST: CROSS JOIN UNNEST(ds.shares) AS t(sharedat, byshared, permission, userid)
```

### 参数类型

| 类型 | SQL 占位符 | 说明 |
|------|-----------|------|
| DATE_RANGE | `${var.start}` / `${var.end}` | 日期范围 YYYY-MM-DD |
| DATE | `${var}` | 单个日期 |
| TIME_MINUTE_RANGE | `${var.start}` / `${var.end}` | 时间范围 YYYY-MM-DD HH:mm |
| TIME_SECOND_RANGE | `${var.start}` / `${var.end}` | 时间范围 YYYY-MM-DD HH:mm:ss |
| NUMBER / NUMBER_RANGE | `${var}` / `${var.min}` `${var.max}` | 数字/数字范围 |
| LIST | `${var}` | 下拉列表（静态 key:value） |
| FILTER_SQL | `${var}` | 下拉列表（动态，基于 Filter SQL 查询结果） |
| TEXT | `${var}` | 文本输入 |

参数来源（source）：
- `CUSTOM`：自定义静态值（LIST / TEXT / NUMBER 等），创建图表时自动推断
- `DIMENSION`：平台维度数据，需指定 `sourceId` 和 `dataType`（如 INT32）。**注意：DIMENSION 源的 quotation 不能通过 API 修改**，需在 SQL 层面处理类型转换
  - keyword 填维度 alias（如 `game_cd`），title 填维度中文名（如 `游戏`）
  - 示例：`{"source": "DIMENSION", "keyword": "game_cd", "title": "游戏", "sourceId": "60d0270962a4005e8b481e1f", "dataType": "INT32", "type": "LIST", "multipleValue": true, "quotation": "SINGLE"}`
  - 常用维度 alias → 名称：game_cd=游戏, bd_country=国家, bd_server_id=角色注册服务器, bd_register_date=注册日期, bd_install_date=安装日期, bd_platform=设备平台, bd_publisher_name=渠道, bd_language=语言, cd_tier=Tier, cd_country_group=国家分组, cd_is_organic=自然量/买量
  - 完整维度列表通过 `GET /dashboard-query/dimensions` 获取
- `FILTER_SQL`：动态下拉列表，基于 Filter SQL 查询结果，需指定 `sourceId`

引号模式（quotation）：`NONE`（日期/数字）、`SINGLE`（单引号，文本列表）、`DOUBLE`（双引号）

### 图表类型与配置

| 类型 | 关键配置 |
|------|---------|
| LINE/BAR/AREA | X轴(类型:category/time/value/log, 名称, 标签旋转), Y轴(左/右双轴, 名称, min/max, 数值格式如0.0%), 系列(图例名, 类型覆盖实现混合图, 颜色), 堆叠, 数据标签 |
| SCATTER | 同上，不支持堆叠 |
| BOXPLOT | 同上 + 是否显示所有点、保留离群点 |
| PIE | 排布方向(顺时针/逆时针), 图例名, 标签格式 |
| HEATMAP | X列, Y列, 颜色列 |
| FUNNEL | 名称列, 数值列, 排序列 |
| TABLE | 列配置(数据类型:文本/数字/日期/布尔/链接/图片/进度条, 对齐, 显隐, 名称), 默认行数, 搜索 |
| COUNTER | 计数值列, 目标值列, 行号, 小数位数, 千位分隔符, 前缀/后缀 |
| PIVOT_TABLE | 分组层级, 行汇总, 列汇总, 字段名自定义 |

标签格式模板：`{{@@name}}`系列名, `{{@@x}}`横轴值, `{{@@y}}`纵轴值, `{{@@yPercent}}`百分比, `{{@@column_name}}`任意列

---

## 3. 创建/更新规则

```
图表: POST /charts → PUT /sql-lab/{id} → POST /charts/charts/{id}/visualization
Dashboard: POST /dashboard-mgr → PUT /dashboard-mgr/{id}（widgets + parameters 全量替换，须同时发送）
paramConfigs: POST /dashboard-mgr/update/param/config 单独更新（PUT 接口不会保存 paramConfigs）
```

- widget 必须包含 `dashboardId`；parameters 需 `widgetParams` 关联 `visualizationId`
- Fork 是最安全的复制方式（完整复制 widgets/parameters/paramConfigs）
- **参数依赖接口需谨慎使用**（`/charts/argument/dependencies/save`），错误的联动 SQL 会导致图表参数无法替换、SQL 报错。使用前务必先通过 `arg-dep-values` 验证 SQL 正确性

---

## 4. 命令参考

### chart.py - 图表操作

```bash
# 创建/更新
python3 skills/dashboard-skill/scripts/chart.py create --name "名称" --sql "SQL" --datasource TRINO_AWS [--tags "标签"] [--sql-file path] [--description "描述"] [--catalog hive]
python3 skills/dashboard-skill/scripts/chart.py update <chart_id> [--name "名称"] [--sql "SQL"] [--sql-file path] [--datasource TRINO_AWS] [--catalog hive] [--tags "标签"]

# 可视化配置
python3 skills/dashboard-skill/scripts/chart.py viz <chart_id> --type LINE --name "图表标题" --x-axis col1 --y-axis "col2,col3" [--group col] [--dashboard <id>]
  # 轴配置
  [--x-axis-type category|time|value|log] [--x-axis-name "名称"] [--x-axis-rotation -45]
  [--y-axis-name "名称"] [--y-axis-min 0] [--y-axis-max 100] [--y-axis-format "0.0%"]
  # 双Y轴
  [--y-axis-right "col4,col5"] [--y-axis-right-name "比率"]
  # 系列
  [--series-type "col3:line,col4:bar"] [--stacked] [--show-label]
  # Counter 专用
  [--count-column col] [--target-column col] [--decimal-places 2] [--prefix "DAU: "] [--suffix " 人"]
  # Heatmap 专用
  [--x-column col] [--y-column col] [--color-column col]
  # Funnel 专用
  [--name-column col] [--value-column col]
  # Pivot Table
  [--show-totals]
  # 高级: JSON 透传（覆盖以上所有选项）
  [--options-json '{"type":"line","xAxis":"date","yAxises":["dau"],"yAxisOption":{"left":{"name":"DAU"}}}']

# 详情/查询
python3 skills/dashboard-skill/scripts/chart.py detail <chart_id> [--from-dashboard <dashboard_id>]
python3 skills/dashboard-skill/scripts/chart.py query <chart_id> [--args '{"key":["v1","v2"]}'] [--async] [--no-cache] [--max-rows 500]
python3 skills/dashboard-skill/scripts/chart.py query <chart_id> --datasource TRINO_AWS --args '...'  # 临时覆盖数据源执行
# 批量查询（传 --dashboard 时不传 --args 会自动从 Dashboard 的 paramConfigs + defaultValues 构建参数）
python3 skills/dashboard-skill/scripts/chart.py query --batch c1,c2,c3 --dashboard d1 [--args '{"param1":["v1"]}']

# 导出数据
python3 skills/dashboard-skill/scripts/chart.py export <chart_id> [--type CSV|EXCEL] [--filename "名称"] [--dashboard <id>] [--args '{}']

# 取消查询
python3 skills/dashboard-skill/scripts/chart.py cancel <task_id>

# 复制图表
python3 skills/dashboard-skill/scripts/chart.py fork <chart_id>

# 批量查询图表详情
python3 skills/dashboard-skill/scripts/chart.py batch-detail <chart_id1> <chart_id2> [--from-dashboard <id>]

# 批量更新数据源（支持别名: TRINO_AWS→TRINO, TRINO_HF→A3_TRINO）
python3 skills/dashboard-skill/scripts/chart.py batch-update-ds <chart_id1> <chart_id2> --datasource A3_TRINO

# 参数依赖（参数联动）
python3 skills/dashboard-skill/scripts/chart.py arg-dep-save <chart_id> --keywords "server_id" --sql "SELECT DISTINCT server_id as name, server_id as value FROM ... WHERE game_cd = '${game_cd}'"
python3 skills/dashboard-skill/scripts/chart.py arg-dep-values <chart_id> --sql "SELECT ..." [--datasource TRINO_AWS]
python3 skills/dashboard-skill/scripts/chart.py arg-dep-delete <chart_id> --keywords "server_id"
```

### cube.py - Cube 图表（数据立方）

```bash
# 元数据查询
python3 skills/dashboard-skill/scripts/cube.py dimensions [--filter "游戏"] [--dashboard <id>]
python3 skills/dashboard-skill/scripts/cube.py indicators [--filter "DAU"] [--dashboard <id>]
python3 skills/dashboard-skill/scripts/cube.py dim-values --alias game_cd [--dashboard <id>]  # 查询维度可选值
python3 skills/dashboard-skill/scripts/cube.py dim-values --id 60d0270962a4005e8b481e1f       # 按维度 ID 查询
python3 skills/dashboard-skill/scripts/cube.py need-data <chart_id> [--dashboard <id>]        # 获取图表所需维度与指标

# Cube 图表 CRUD
python3 skills/dashboard-skill/scripts/cube.py create --name "名称" --dimensions "dim_id1,dim_id2" --indicators '[{"id":"xxx"}]' [--tags "标签"]
python3 skills/dashboard-skill/scripts/cube.py detail <chart_id> [--from-dashboard <id>]
python3 skills/dashboard-skill/scripts/cube.py query <chart_id> [--dashboard <id>] [--args '{"game_cd":["1047"]}'] [--no-cache] [--max-rows 500]
```

### dashboard.py - Dashboard 操作

```bash
python3 skills/dashboard-skill/scripts/dashboard.py detail <id> [--include-charts]

# 查询可访问的 Dashboard（我的 + 分享给我，支持按名称/标签过滤）
# 返回精简信息：名称、标签、最后更新人（ID 视接口是否返回）
python3 skills/dashboard-skill/scripts/dashboard.py accessible [--keyword "关键词"]

# 检查 Dashboard 组件未配置参数源的参数（config-params 后可用于验证）
python3 skills/dashboard-skill/scripts/dashboard.py parameter-check <dashboard_id>

# 创建（默认关闭自动查询）
python3 skills/dashboard-skill/scripts/dashboard.py create --name "新Dashboard" [--tags "标签"] [--description "描述"] [--auto-query]

# 复制 / 克隆修改
python3 skills/dashboard-skill/scripts/dashboard.py fork <source_id> [--no-charts]
python3 skills/dashboard-skill/scripts/dashboard.py clone-and-modify <source_id> --name "名称" --sql-mapping '{}' --date-range '[]'

# 更新
python3 skills/dashboard-skill/scripts/dashboard.py update <id> [--name "名称"] [--tags "标签"] [--description "描述"] [--param-configs 'JSON']
  [--parameters 'JSON']  # Dashboard 级别 parameters 全量替换（手动覆盖，一般用 config-params 自动配置）
  [--auto-query | --no-auto-query]

# 自动配置参数源（add-chart 后必须执行）
python3 skills/dashboard-skill/scripts/dashboard.py config-params <id>
  # 自动完成：读取所有图表参数 → 构建全局参数 + widgetParams 关联 → 初始化 paramConfigs

# 添加组件
python3 skills/dashboard-skill/scripts/dashboard.py add-chart <id> chart1 chart2
python3 skills/dashboard-skill/scripts/dashboard.py add-text <id> --text "一、核心指标" [--width 6] [--height 2] [--no-center]
  # 默认居中显示（<center><font size=24px>），传 --no-center 则保留原始文本

# 用户搜索 & 权限查询
python3 skills/dashboard-skill/scripts/dashboard.py search-user "名字"
python3 skills/dashboard-skill/scripts/dashboard.py user-dashboards "名字"  # 查询用户拥有+被分享的所有 Dashboard

# 权限分享（permission: 1=查看(默认), 2=编辑, 3=编辑+分享）
# 重复分享同一用户会覆盖权限（幂等），无需先取消再重新分享。升级/降级权限直接传新 permission 即可
python3 skills/dashboard-skill/scripts/dashboard.py share <id> <uid1> [uid2] [--permission 1|2|3] [--no-share-charts]
python3 skills/dashboard-skill/scripts/dashboard.py share <id> --name "名字" [--permission 1]  # 按姓名自动查找并分享（唯一匹配时直接分享，多人匹配返回候选列表）
python3 skills/dashboard-skill/scripts/dashboard.py shared-users <id>
python3 skills/dashboard-skill/scripts/dashboard.py cancel-share <id> <uid>  # 完全取消分享（不是降级，是移除权限）
```

### filter_sql.py - 筛选器 SQL

```bash
python3 skills/dashboard-skill/scripts/filter_sql.py list [--name "关键词"]
python3 skills/dashboard-skill/scripts/filter_sql.py get <id>
python3 skills/dashboard-skill/scripts/filter_sql.py create --name "名称" --sql "SELECT name, value FROM ..." [--datasource TRINO_AWS] [--db hive]
python3 skills/dashboard-skill/scripts/filter_sql.py update <id> [--name "名称"] [--sql "SQL"] [--datasource TRINO_AWS] [--db hive]
python3 skills/dashboard-skill/scripts/filter_sql.py execute <id>
python3 skills/dashboard-skill/scripts/filter_sql.py test --sql "SELECT 'ALL' as name, 'ALL' as value" [--datasource TRINO_AWS]  # 保存前测试
python3 skills/dashboard-skill/scripts/filter_sql.py batch-update-ds <id1> <id2> --datasource A3_TRINO  # 批量更新数据源
```

Filter SQL 格式要求：
- 必须返回两列：`name`（下拉列表显示值）和 `value`（传入后台的实际值）
- 通常添加 ALL 选项：`SELECT 'ALL' as name, 'ALL' as value UNION ALL SELECT ...`

---

## 5. Dashboard 开发流程

### 5.0 需求分析与开发计划（每次开发前必须执行）

收到 Dashboard 开发需求后，禁止直接开始开发。必须先完成以下分析，输出开发计划给用户确认：

```
Phase 1: 理解需求
    - 明确要展示什么数据、给谁看、解决什么问题
    - 阅读用户提供的数据源代码/文档/表名，理解数据流和表结构
    - 如果用户提供了 ETL 代码，重点关注最终产出表和关键字段
    ↓
Phase 2: 梳理数据源
    - 确定目标表及其所在数据源（Trino 直查 / Doris 通过 doris.库名.表名 访问）
    - 列出关键字段、数据粒度、分区方式
    - 如需探索表结构，使用 ai-to-sql 的 explore_tables.py
    ↓
Phase 3: 规划图表
    - 列出每个图表：名称、类型（LINE/BAR/TABLE/PIE 等）、数据来源表、关键列
    - 明确哪些是趋势图、哪些是明细表、哪些是汇总统计
    ↓
Phase 4: 规划参数与筛选
    - 确定全局参数（日期范围、游戏筛选等）
    - 优先使用平台已有维度（如 game_cd 来源：维度→基础属性→游戏），仅在无现成维度时创建 Filter SQL
    - 游戏筛选规则：
      · 统一使用平台维度（维度→基础属性→游戏），类型为下拉列表
      · 是否允许多选取决于实际数据场景（如 SQL 中用 IN 则多选，用 = 则单选）
      · 用户明确指定了目标游戏 → 在候选项中只勾选指定的游戏，而非"默认为全部"
      · 用户未指定游戏 → 候选项使用"默认为全部"
    - 明确每个参数的类型（DATE_RANGE / LIST / FILTER_SQL 等）和引号模式
    ↓
Phase 5: 输出开发计划（必须包含以下内容）
    - 数据源：表名、数据源类型、关键字段
    - 图表清单：每个图表的名称、类型、SQL 数据来源、关键列
    - 参数清单：参数名、类型、来源（平台维度 or 自建 Filter SQL）
    - Dashboard 名称
    - 执行步骤概要
    ↓
Phase 6: 提出待确认问题
    - 数据源访问方式不确定时提问
    - 业务逻辑有歧义时提问
    - 图表展示方式有多种选择时列出选项
    - 筛选维度是否有现成的平台维度可用
```

用户确认开发计划后，再进入 5.1 完整开发流程执行。

### 5.1 完整开发流程

```
Step 1: 探索数据 → 开发 SQL → 执行验证
    使用 ai-to-sql 技能完成 SQL 开发（详见第 6 章）
    SQL 必须执行不报错才能进入下一步
    ↓
Step 2: 创建图表 → 立即查询验证
    python3 skills/dashboard-skill/scripts/chart.py create --name "图表名" --sql "验证通过的SQL" --datasource TRINO_AWS
    - 设置名称：简明扼要，格式【游戏代号】具体内容
    - 设置 tag：最多 1 个，项目组用游戏编码（如 X1），平台用平台名（如 onehub）
    ** 创建后立即查询验证（必须）**：
    python3 skills/dashboard-skill/scripts/chart.py query <chart_id> --args '{"report_date":["2026-03-18","2026-03-25"]}'
    - 图表必须查询成功且返回数据才能进入下一步
    - 查询失败则检查 SQL 并用 chart.py update 修复后重新验证
    ↓
Step 3: 配置可视化（必须设置名称和坐标含义）
    python3 skills/dashboard-skill/scripts/chart.py viz <chart_id> --type LINE --name "图表标题" --x-axis col1 --y-axis "col2,col3"
    - 必须设置 --name：图表在 Dashboard 中显示的标题
    - 必须设置 --x-axis-name 和 --y-axis-name：横纵坐标的含义说明
    - 设置展示图例（--group 分组列）
    - 百分比数据用 --y-axis-format "0.0%"（自动将 0.1234 显示为 12.3%）
    - 需要双Y轴时用 --y-axis-right 指定右轴列
    - 混合图（折线+柱状）用 --series-type "col1:line,col2:bar"
    - 需要备注时添加备注，根据实际情况调整数值类型格式
    ↓
Step 4: 创建 Filter SQL（仅在平台无现成维度时）
    python3 skills/dashboard-skill/scripts/filter_sql.py create --name "筛选器名" --sql "SELECT name, value FROM ..."
    - 优先使用平台已有维度数据（如 game_cd：维度→基础属性→游戏，下拉列表+多选）
    - 用户指定了目标游戏时，在维度候选项中只勾选指定游戏，而非"默认为全部"
    - 只有当平台维度不满足需求时，才自己创建 Filter SQL
    - 必须返回 name 和 value 两列
    - 数据中一般添加 ALL 选项
    - filter 关键字简明扼要
    ↓
Step 5: 创建 Dashboard 并添加图表
    python3 skills/dashboard-skill/scripts/dashboard.py create --name "【X1】xxx数据分析"
    python3 skills/dashboard-skill/scripts/dashboard.py add-chart <dashboard_id> chart1 chart2 chart3
    注意：创建时默认关闭自动查询（autoQuery=false），避免打开时自动执行所有图表
    ↓
Step 6: 配置参数源 + 验证（add-chart 后必须执行）
    python3 skills/dashboard-skill/scripts/dashboard.py config-params <dashboard_id>
    - 自动完成：读取所有图表参数 → 构建全局参数 + widgetParams 关联 → 初始化 paramConfigs
    - add-chart 不会自动配置参数源，必须手动执行此命令
    - 如需手动调整参数（如修改 defaultValues、显隐），再用 update --param-configs 'JSON'
    配置后验证 Dashboard 参数是否完整（必须）：
    python3 skills/dashboard-skill/scripts/dashboard.py parameter-check <dashboard_id>
    - 确认 problematicCount=0（无缺失参数源的组件）
    - 图表本身已在 Step 2 逐个查询验证过，此处只需检查 Dashboard 参数配置
    ↓
Step 7: 分章节与文字说明
    python3 skills/dashboard-skill/scripts/dashboard.py add-text <dashboard_id> --text "一、核心指标"
    python3 skills/dashboard-skill/scripts/dashboard.py add-text <dashboard_id> --text "以下图表展示..." --no-center
    - 默认居中 + 24px 字号（适合章节标题），--no-center 保留原始文本（适合长段说明）
    ↓
Step 8: 交付反馈
    确认无错误后，反馈给用户：
    - Dashboard 名称及访问地址
    - 创建了哪些图表内容
    - 创建或使用了哪些 Filter SQL
    - 询问用户是否需要将此 Dashboard 分享给其他人
```

### 5.2 克隆修改流程（基于已有模板）

```bash
# 1. 查看模板详情
python3 skills/dashboard-skill/scripts/dashboard.py detail <source_id> --include-charts

# 2. 克隆并修改
python3 skills/dashboard-skill/scripts/dashboard.py clone-and-modify <source_id> \
  --name "KOW 2026-02 新年活动数据" \
  --sql-mapping '{"christmas_event":"newyear_event","2025-12":"2026-02"}' \
  --date-range '["2026-02-01","2026-02-28"]'

# 3. 验证图表查询
python3 skills/dashboard-skill/scripts/chart.py query <chart_id> --args '{"report_date":["2026-02-01","2026-02-28"]}'
```

### 5.3 查询分析已有 Dashboard

```
Step 1: 获取 Dashboard 详情
    python3 skills/dashboard-skill/scripts/dashboard.py detail <id> --include-charts
    → 关注: 图表列表(widgets)、parameters、paramConfigs（当前筛选值）、charts（SQL和参数定义）
    ↓
Step 2: 确认查询参数
    - 默认使用 paramConfigs 的当前值作为查询参数
    - 如用户指定了筛选条件，覆盖对应参数
    - 检查所有图表参数是否都有值覆盖（paramConfigs 可能不完整，缺失的从 parameters.defaultValues 补齐）
    - ⚠️ 部分图表可能有特有参数（如 hero_id、shipID、asset_id 等下钻参数），不在全局 parameters 中
      → 这些图表在 batch 查询中会因参数缺失被自动跳过，返回 skipped + missingParams
      → 如需查询，需在 --args 中显式提供这些参数值
      → 或在分析报告中说明"以下 N 个图表需要手动选择具体对象，本次未纳入分析"
    ↓
Step 3: 批量查询图表数据
    python3 skills/dashboard-skill/scripts/chart.py query --batch chart1,chart2 --dashboard <id> --args '{"param1":["v1"]}'
    - 传 --dashboard 时不传 --args 会自动从 paramConfigs + defaultValues 构建参数
    - 如需覆盖特定参数值，通过 --args 显式传入
    - 单图表查询: chart.py query <chart_id> --dashboard <id> --args '{...}'
    ↓
Step 4: 数据分析与汇报
    - 从汇总到明细，多维度拆解
    - 指出异常值和关键发现
    - 给出可操作建议
```

---

## 6. 编写代码流程（SQL 开发）

当需要为 Dashboard 图表编写 SQL 时，使用 ai-to-sql 技能的工具链完成 SQL 开发。**禁止跳过检索直接写 SQL**，必须按以下流程执行：

```
Step 1: 初始化 — 获取游戏权限（每次会话仅需执行一次）
    python3 skills/ai-to-sql/scripts/get_game_info.py
    → 获取 full_access / game_cds / datasource / tables
    ↓
Step 2: 检索知识库（必须执行）
    python3 skills/ai-to-sql/scripts/rag_search.py \
      --query "关键词" --game_cd 游戏编码 --source metrics
    → 大量业务查询都有现成 SQL 逻辑，优先基于参考 SQL 改写
    → 业务概念不清楚时加 --source all 同时检索 wiki
    ↓
Step 3: 探索表结构
    python3 skills/ai-to-sql/scripts/explore_tables.py \
      --tables "表名1,表名2" --datasource TRINO_AWS|TRINO_HF
    → 确认字段名、类型、分区信息
    → 参考 SQL 中的表名、字段名优先采信
    ↓
Step 4: 生成 SQL 并验证
    python3 skills/ai-to-sql/scripts/query_trino.py \
      --sql "SELECT ..." --datasource TRINO_AWS|TRINO_HF --limit 100
    → 所有 SQL 必须先执行验证通过，失败则修复后重试
    ↓
Step 5: 创建图表 → 查询验证 → 配置可视化 → 添加到 Dashboard
    python3 skills/dashboard-skill/scripts/chart.py create --name "图表名" --sql "验证通过的SQL" --datasource TRINO_AWS
    python3 skills/dashboard-skill/scripts/chart.py query <chart_id> --args '{"report_date":["2026-03-18","2026-03-25"]}'
    → 创建后立即查询，确认图表能正常返回数据，失败则 update 修复后重试
    python3 skills/dashboard-skill/scripts/chart.py viz <chart_id> --type LINE --name "图表标题" --x-axis col1 --y-axis "col2,col3" --x-axis-name "日期" --y-axis-name "数量"
    python3 skills/dashboard-skill/scripts/dashboard.py add-chart <dashboard_id> <chart_id>
```

### 6.1 SQL 开发规范

遵循 ai-to-sql 的 SQL 生成规范（详见 ai-to-sql SKILL.md 第 5 章）：

1. **必须先检索指标参考**，优先基于参考 SQL 改写，而非从零编写
2. 所有表必须加别名（小写），SQL 结尾不加分号
3. 有分区字段的表**必须**加分区过滤（ods/dl: `partition_date`，stg: `create_date`）
4. 用户未指定日期时，默认查询近 7 天
5. `full_access=false` 的用户，tables 已自动转换为视图占位格式 `{catalog}.v{game_cd}.{layer}_{table}`（如 `hive.v{game_cd}.ods_user_login`），生成 SQL 时将 `{game_cd}` 替换为实际游戏编码，且无需 `WHERE game_cd = xxx`
6. `full_access=true` 的用户直接查原表，需加 `WHERE game_cd = xxx`
7. TRINO_HF 环境下 stg 层表需加 `hive.` 前缀
8. 字段别名含中文用双引号，浮点除法用 `1.00 * 被除数 / 除数`
9. **SQL 中的日期参数使用 `${变量名.start}` / `${变量名.end}` 占位符**，以便 Dashboard 筛选器联动
10. **更新图表 SQL 必须通过 `chart.py update` 命令**，不要直接调用 `PUT /sql-lab/{id}` API — 直接调 API 不传 `arguments` 字段会清空已有参数，`chart.py update` 会自动推断并保留参数

### 6.2 完整示例：为 KOW 创建 DAU 趋势图并添加到 Dashboard

```bash
# 1) 获取权限信息
python3 skills/ai-to-sql/scripts/get_game_info.py

# 2) 检索 DAU 相关的参考 SQL
python3 skills/ai-to-sql/scripts/rag_search.py --query "DAU 活跃用户 趋势" --game_cd 1038 --source metrics

# 3) 探索表结构确认字段
python3 skills/ai-to-sql/scripts/explore_tables.py --tables "ods.user_login" --datasource TRINO_AWS

# 4) 基于参考 SQL 改写，先用固定日期验证
python3 skills/ai-to-sql/scripts/query_trino.py --datasource TRINO_AWS --sql "
SELECT partition_date as report_date,
       count(distinct open_udid) as dau
FROM ods.user_login a
WHERE a.game_cd = 1038
  AND a.partition_date BETWEEN '2026-03-13' AND '2026-03-20'
GROUP BY partition_date
ORDER BY partition_date
" --limit 100

# 5) SQL 验证通过后，将固定日期替换为 ${} 占位符，创建图表
python3 skills/dashboard-skill/scripts/chart.py create \
  --name "【KOW】每日DAU趋势" \
  --sql "SELECT partition_date as report_date, count(distinct open_udid) as dau FROM ods.user_login a WHERE a.game_cd = 1038 AND a.partition_date BETWEEN '\${report_date.start}' AND '\${report_date.end}' GROUP BY partition_date ORDER BY partition_date" \
  --datasource TRINO_AWS --tags "KOW"

# 5.1) 创建后立即查询验证
python3 skills/dashboard-skill/scripts/chart.py query <chart_id> --args '{"report_date":["2026-03-13","2026-03-20"]}'

# 6) 创建折线图可视化
python3 skills/dashboard-skill/scripts/chart.py viz <chart_id> --type LINE \
  --name "【KOW】每日DAU趋势" --x-axis report_date --y-axis dau \
  --x-axis-type time --x-axis-name "日期" --y-axis-name "DAU"

# 7) 添加到 Dashboard
python3 skills/dashboard-skill/scripts/dashboard.py add-chart <dashboard_id> <chart_id>
```

### 6.3 多图表开发流程

当需要一次性为 Dashboard 创建多个图表时：

1. Step 1-3 只需执行一次（权限、检索、表结构探索可复用）
2. 每个图表分别执行 Step 4（验证 SQL）和 Step 5（创建图表 + 可视化）
3. 最后批量添加到 Dashboard：`python3 skills/dashboard-skill/scripts/dashboard.py add-chart <dashboard_id> chart1 chart2 chart3`

---

## 7. 命名规范

格式：`【游戏代号】具体内容描述`

| 错误 | 正确 |
|------|------|
| 【X9】核心数据概览 | 【X9】每日DNU·DAU·付费·在线数据总览 |
| 【KOW】活动Dashboard | 【KOW】2026-02新年活动参与率与付费转化 |

原则：用户给了名称直接用；没给时必须具体到指标/维度；始终带【游戏代号】前缀；禁用"概览、核心、数据、报表、Dashboard"等空泛词。

## 8. 协作 Skill

- **ai-to-sql**：SQL 开发核心技能 — 知识库检索（指标参考 + wiki）、表结构探索、SQL 生成与验证执行。编写图表 SQL 时必须使用此技能的工具链，详见[第 6 章 编写代码流程](#6-编写代码流程sql-开发)
