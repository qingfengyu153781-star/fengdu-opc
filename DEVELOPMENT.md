# 枫独 · OPC 经营助手 — 开发文档

> 版本：v1.0（GOAI 初赛 Demo）｜最后更新：2026-08-06
> 所属：GOAI 世界人工智能开源大赛 · 无界应用｜BoundlessAgents · AI+金融 赛道
> 定位：面向一人公司（OPC = One Person Company）的经营辅助 Agent，让没有财务/法务背景的普通人也能把公司开明白。

本文档面向**后续开发与复赛迭代**：说明代码为什么这么写、每个模块怎么改、怎么加新地区、怎么部署、怎么保证演示不翻车。建议配合 `README.md`（使用视角）与 `../05_研究笔记_AI经营顾问.md`（产品视角）阅读。

---

## 一、产品与技术一句话

**产品**：用户输入经营情况 → 系统匹配可申请政策 → 预审材料清单 → 提示资格风险。核心是「材料预审 + 经营诊断」闭环。

**技术**：**联网搜索匹配（核心）+ 规则判定资格 + LLM（语义理解）** 的混合架构，不是纯聊天机器人。

- **核心 = 联网搜索当地政策**（Bing/DDG/百度 多源，可配 Bing API/SearXNG 更稳）→ 规则判定资格 → 材料清单 → 风险提示。
- **LLM 负责理解**：语义抽取任意行业/地区、生成精准搜索词、合规问答、政策导入结构化（不是可有可无的"增强"，是理解层）。
- **断网保底**：联网搜索不可用（断网/受限）时降级本地通用库 + 规则引擎 → 不白屏、不造假（保命兜底，非核心卖点）。

---

## 二、技术架构总览

```
用户一句话经营描述
  → [business_profile 追问状态机]  缺哪些必填字段 → 逐项追问（主动询问，不依赖一次说清）
  → [rule_engine 政策匹配]          三态判定（match/no/unknown）→ 材料清单 → 缺项/格式检测
  → [state_model 状态模型]          6 维状态向量 → 三指数（健康 H / 政策机会 P / 风险 R）
  → [app.py 驾驶舱 UI]             实时可视化 + 来源引用 + 风险提示
```

| 层 | 模块 | 职责 | 确定性 |
|----|------|------|:--:|
| 输入理解 | `utils/business_profile.py` | 18 字段经营信息模型 + 追问状态机 + 句法模式抽取（零值枚举） | ✅ 规则 |
| 政策匹配 | `utils/rule_engine.py` | 资格条件逐条判定、材料清单、风险评估 | ✅ 规则 |
| 经营诊断 | `utils/state_model.py` | 6 维状态向量 + 三指数（透明可解释） | ✅ 规则 |
| 实时搜索 | `utils/policy_searcher.py` | 未收录地区实时搜索当地政策（Bing→DDG→百度） | ✅ 规则 |
| LLM（语义理解） | `utils/api_client.py` | ModelScope 免费推理 API，4 模型 fallback 链；负责任意行业/地区理解、搜索词生成、合规问答 | ⚠️ 有 key 才用 |
| 提示词 | `prompts/agent_prompts.py` | 6 组 prompt 模板（人格/追问/抽取/解释/问答/导入） | ⚠️ 有 key 才用 |
| 政策数据 | `policies/` | 按地区分库（national 通用 + 温州真实 + 杭州占位 + general 兜底） | ✅ 数据 |
| UI 入口 | `app.py` | Gradio 6.x 枫叶主题，4 个 Tab + 驾驶舱 | — |

---

## 三、目录结构

```
demo/
├── app.py                # Gradio 入口（枫叶主题 · 4 Tab + 驾驶舱渲染）
├── requirements.txt      # gradio>=6.0, openai>=1.30, requests
├── assets/               # 视觉素材（logo/banner/bg/leaf/region_banner，base64 内嵌）
├── policies/             # 政策库（单一真相源）
│   ├── __init__.py       # 地区注册表 REGIONS + all_policies() 组装
│   ├── national.py       # 国家级通用 4 项（任何地区自动叠加）
│   ├── wenzhou.py        # 温州 11 项（S1-S11，真实数据，默认完整示范）
│   ├── hangzhou.py       # 杭州（示例占位·待核对）
│   ├── general.py        # 通用政策方向（未收录地区兜底，零造假）
│   └── region_template.py# 新地区模板
├── utils/
│   ├── business_profile.py # 18 字段模型 + 追问状态机 + 句法/数字抽取（零值枚举）
│   ├── rule_engine.py    # 政策匹配（三态）+ 材料清单 + 风险评估
│   ├── state_model.py    # 6 维状态向量 + 三指数
│   ├── policy_searcher.py# 实时政策搜索（零 key，多源）
│   └── api_client.py     # ModelScope LLM fallback 链 + mock 降级
├── prompts/
│   └── agent_prompts.py  # 6 组 prompt 模板
├── README.md             # 使用说明 + 部署
├── DEVELOPMENT.md        # 本文档
├── 演示脚本.md            # 一镜到底 Demo 视频脚本
└── 启动.bat / 启动说明.txt # Windows 双击启动
```

---

## 四、核心数据流

### 4.1 材料预审（Tab ①，主线闭环）

```
process_chat(user_text, profile, chat, region)
  │
  ├─ 规则抽取字段（extract_from_text，句法模式+封闭选项，零值枚举；LLM 有 key 时优先理解）
  ├─ 兜底抽取（回答当前被问字段但没抽到 → yes/no / 宽松数字 / 短文本直录）
  ├─ 地区判定：用户消息里说的城市 > 下拉当前值 > 已有值
  │
  ├─ 若追问未完成（必填缺失 + 关键非必填 grad_year/team_size 未填，P4）→ next_question()
  │     · LLM 可用 → polish_question() 润色成大白话
  │     · LLM 不可用 → 直接给规则问题（自带选项提示）
  │     · 同步渲染「采集进度」驾驶舱
  │
  └─ 若追问完成（必填 + 关键非必填齐或已跳过）→ 出报告：
        summary(profile, region)     # 匹配政策 + 材料清单 + 风险
        compute_indices(profile, region)  # 三指数
        render_report()               # 政策/材料/风险三段文本
        render_cockpit()              # 驾驶舱 HTML
        （未收录地区）→ policy_searcher 实时搜索 + 可选 LLM 政策方向
```

### 4.2 经营诊断（Tab ②）

填表（或一键带入摄影师示例）→ `run_diagnosis` → 同上 summary + compute_indices → 驾驶舱 + 报告。缺必填字段时返回缺项提示，不白屏。

### 4.3 合规问答（Tab ③）

实时联网搜索（免费）→ LLM 回答（有 key）→ 失败回退 `COMPLIANCE_MOCK` 知识库 + 网页结果。**离线也能答基础问题。**

### 4.4 政策导入（Tab ④）

粘贴政策原文 → 优先 LLM 结构化（JSON）→ 失败回退规则解析（`_parse_policy_rules`，零 key）→ 写入 `policies/<code>.py` + 注册进 `REGIONS` → 重启后地区下拉可用。

---

## 五、模块详解

### 5.1 `policies/` — 政策库（单一真相源）

**一条政策的完整结构**（`wenzhou.py` / `region_template.py` 为准）：

```python
{
    "id": "S1",                    # 唯一 ID（导入政策用 IMP-N）
    "name": "一次性创业补贴（市级）",
    "region": "wenzhou",           # 归属地区 code
    "category": "创业启动",         # 创业启动 / 社保生活 / 资质税务 / 其他
    "amount": "¥100,000",          # 金额/力度（原文口径）
    "eligibility": ["毕业 5 年内高校毕业生", "在温州注册 OPC 公司", "正常经营"],
    "materials": [                 # 材料清单
        {"name": "营业执照", "required": True, "format_note": "格式说明（可选）"},
    ],
    "source": "温州人社局创业服务窗口",   # 来源机构（可溯源）
    "source_url": "https://www.zjzwfw.gov.cn/",
    "difficulty": "低",            # 低 / 中 / 高
    "timing": "公司注册后即可申请",
    "key_point": "必须先注册公司再申请（不能反过来）",
    "update_date": "2026-07",
}
```

**组装规则**（`__init__.py`）：

- `REGIONS = {wenzhou, hangzhou}` —— 只有演示用真实库。
- `all_policies(region)` = **national + 该地区**；未收录地区 = **national + general**。
- `FALLBACK_REGION = general` —— 通用政策方向兜底，`data_status` 标「通用参考·需核验」，**不计入「政策机会」数字**（零造假）。

**当前库量**：national 4 项（N1-N4）、温州 11 项（S1-S11）、杭州占位、general 若干方向。

> ⚠️ 数据诚实铁律：只收录真实政策。杭州库是「示例占位·待核对」，不填充编造内容。

### 5.2 `utils/business_profile.py` — 字段模型 + 追问状态机

**18 个经营信息字段**（`FIELDS`），`required=True` 的 7 个（region / reg_type / social_security / education / duration / revenue / industry），按 `priority` 排序追问。

| 维度 | 字段（key） |
|------|------------|
| 基础 | region、reg_type、education、grad_year、industry |
| 经营 | duration、revenue、cost、order_cycle、continuity |
| 财务健康 | cash_buffer、client_concentration、team_size、corp_account |
| 政策相关 | social_security、biz_scope_ai、risk_items、has_materials |

**追问状态机**（核心是「主动询问」，不依赖一次说清）：

- `missing_fields(profile)`：按 priority 返回缺失的必填字段。
- `next_question(profile)`：返回第一个缺失字段的 `ask` 问题；全齐返回 None。
- `is_complete(profile)`：必填字段是否齐全。

**抽取架构（v2，零值枚举）**：LLM 理解为主，规则只做兜底。

- **有 `MODELSCOPE_API_KEY`**：`app.llm_extract_profile` 用模型理解任意表达（不穷举），`EXTRACT_PROMPT` 明确要求 region/industry 是开放值、输出原话、不映射固定表。
- **无 key / LLM 失败**：`extract_from_text` 兜底，**零值枚举**——不预置任何城市/行业表：
  - `_SPECIAL_PARSERS["region"]`：纯句法模式（"在XX经营/注册""我是温州个体工商户"→注册类型标记前的词为地区）。守卫：捕获词含动作动词（"我是做摄影的个体户"）→ 拒绝，交给下拉兜底，绝不猜错地区。
  - `_SPECIAL_PARSERS["industry"]`：**已删除关键词表**。行业是开放值，统一走 `extract_industry_free` 纯句法模式（"我(做|是|开)XXX"抓原文，任意行业可识别）。
  - 封闭选项字段（reg_type/social_security/education/biz_scope_ai/corp_account）：按字段自带 `options` 匹配，不算穷举。
    - **坑点**：social_security 正则里 `有|交|缴` 最后兜底，但**特意不含「是」**——"我是XX"的"是"会误判为有社保。
  - `_NUMBER_PARSERS`：数字型字段（revenue/duration/cash_buffer/grad_year/team_size/client_concentration/order_cycle），支持中文数字（`_cn_to_int` / `_cn_to_num_text`，含"万/千/百/十"）。
  - `extract_loose_number`：追问兜底时从回答里提第一个数字（revenue 无单位按"元/月"，duration 无单位按"年"）。
  - `parse_yes_no`：通用有/无解析（有/没有/交了/没交 → 有/无）。
  - `parse_llm_json`：解析 LLM 抽取输出（去 ```json``` 块、截取 `{...}`、只留已知字段）。

> 修改字段清单 = 改 `FIELDS` 数组即可，追问状态机、驾驶舱进度、抽取都自动跟随。

### 5.3 `utils/rule_engine.py` — 规则引擎

**匹配三态**（`_check_condition`）：

| 状态 | 含义 | 驱动 |
|------|------|------|
| `match` | 条件满足，可申请 | 政策机会指数 + 材料清单 |
| `no` | 条件不满足（阻塞） | 标注原因 + 替代路径 |
| `unknown` | 缺信息，需追问 | 驱动多轮主动询问 |

**判定覆盖的条件类**：学历（本科及以上）、毕业窗口（5 年内）、地区、注册类型（独立法人/OPC/公司）、经营时长（X 年以上/满 X 个月）、社保、招用员工、应纳税所得额/月销售额/人数/资产上限、个体户/小型微利/小规模纳税人、研发/软著/软件收入占比、大赛获奖、无住房、入驻 OPC 中心、算力采购、合同付款等。**未识别的条件返回 `unknown` +「需人工确认」，绝不猜。**

**政策级状态聚合**（`match_policies`）：

```
有 unmet 条件 → no
否则有 pending（unknown）→ unknown
否则 → match
```

- `matched_policies(profile, region, include_national)`：返回 match 的政策。`include_national=False` 只算地区差异化（**政策机会指数专用**，国家级人人都有不算机会）。
- `policy_match_rate`：match / (match + no)，排除 unknown。

**材料清单**（`build_checklist`）：

- 只收 `match` + `unknown` 政策（`no` 被资格否决的不列，`general` 通用参考不列）。
- 材料去重（`_norm_material` 去掉括号注释，如"经营场所证明（OPC中心入驻协议即可）"与"经营场所证明"视为同一材料）。
- 状态四档：`缺失 > 待确认 > 已备 > 自动`（自动 = 告知性条目"系统自动享受"，不参与待办统计）。

**风险评估**（`assess_risk`）：

- 三类风险：客户集中（≥50% 高/≥30% 中）、社保缺口（无社保）、现金流缓冲（<3 月高/<6 月中）。
- 综合等级特判（对齐 PPT「风险中·重点关注」语义）：
  - 现金流 <3 月 **或** 单一客户 >80% → 综合「高」
  - 有高优先级风险项但现金流安全（≥3 月）→ 综合「中」（重点关注，不是致命）
  - 摄影师示例（单客户60% + 现金4个月）→ 综合「中」✅

### 5.4 `utils/state_model.py` — 状态模型（核心创新）

**6 维状态向量**（`build_state_vector`）：

| # | 维度 | 判定 |
|---|------|------|
| 1 | 个人依赖度 | 团队≤1 高 / ≤3 中 / 否则低 |
| 2 | 收入来源集中度 | 单客户≥50% 高 / ≥30% 中 / 否则低 / 缺数据待评估 |
| 3 | 订单生命周期 | 有订单周期 中 / 缺数据 待评估 |
| 4 | 客户集中风险 | ≥50% 高风险 / ≥30% 中 / 否则低 |
| 5 | 现金流缓冲能力 | ≥6 月强 / ≥3 月中 / 否则弱 / 缺数据待评估 |
| 6 | 经营连续性 | ≥2 年中 / ≥1 年中 / <1 年低 / 缺数据待评估 |

**三指数**（`compute_indices`，公开可解释，非黑盒）：

```
健康指数 H = 5 维等权 20% 取平均（round）
  维度：收入稳定(客户集中) / 现金流安全(缓冲月数) / 成本控制(成本/营收比)
       / 政策匹配(地区差异化可申请数) / 经营周期(经营年数)
  每维带打分理由（score, reason, weight=20%）

政策机会指数 P = 地区差异化可申请政策数（include_national=False）
风险指数 R = 规则引擎综合风险等级（低/中/高）
```

**示例**（摄影师：个体户/摄影/2年/月入3万/社保无/现金4个月/单客户60%/1人/本科/2022）：**健康 72 / 政策机会 3 / 风险中** —— 与 PPT P6/P7 一致，是验收基准。

### 5.5 `utils/policy_searcher.py` — 实时政策搜索

- **多源尝试**：Bing → DuckDuckGo → 百度，逐个尝试，全部失败返回空列表。
- **零造假**：返回的是搜索引擎真实结果（标题+URL+摘要），带来源可溯源；摘要来自搜索结果页，提示"需点开核验"。
- **`generate_query(region, profile, llm_fn)`：零值枚举搜索词**（核心：搜索词=模型理解，不是类目穷举）。
  - LLM 可用 → 根据行业+经营特点生成精准搜索词（覆盖任意行业，不映射固定类目表）。
  - LLM 不可用 → 用户原话行业词直接拼（`{region} {行业} 创业 补贴 政策 2026`），跟 business_profile 同哲学。
- `search_policies(region, keyword)`：多轮补搜（配真后端时最多 3 轮，免费爬虫 1 轮）。
- `search_and_format` / `format_web_search`：格式化成报告段落，失败返回空串（由上层回退通用库）。

> ⚠️ 创空间若限制外网出站，搜索可能失败 → 架构已兜底（回落通用库 + LLM），不白屏。属正常降级。

### 5.6 `utils/api_client.py` — LLM fallback 链

- 端点：`https://api-inference.modelscope.cn/v1/`（OpenAI 兼容协议）。
- **fallback 链**：`Qwen3-235B-A22B-Instruct-2507 → Qwen3-235B-A22B → Qwen3-30B-A3B-Instruct-2507 → Qwen3-8B`。
- `is_api_available()`：无 `MODELSCOPE_API_KEY` 时返回 False → LLM 语义理解不可用，降级句法抽取 + 规则匹配（保底，非核心）。
- 参数：TIMEOUT=60、MAX_ATTEMPTS=2（演示场景 2 轮足够，等太久会白屏）、指数退避 `sleep(2**attempt)`、`enable_thinking=False`。
- 两个入口：`chat()`（多轮，合规问答/追问润色）、`generate()`（单轮低温度，政策导入结构化）。

### 5.7 `prompts/agent_prompts.py` — 提示词

统一人格 `SYSTEM_BASE`：定位是辅助顾问不是审批机构，**禁止编造政策/金额/资格、禁止打包票、禁止确定性投资/贷款/赔付结论**，所有输出带来源 +「辅助参考」边界。

6 组模板：
1. `Q_A_PROMPT` 追问润色（一次只问一个、大白话、解释为什么问、30 字内）
2. `EXTRACT_PROMPT` 非结构化抽取（只输出 JSON，识别到才填）
3. `EXPLAIN_PROMPT` 政策推荐解释（先说结论 → 大白话条件 → 点 1 个坑 → 来源引用）
4. `COMPLIANCE_PROMPT` 合规问答（能引则引、不确定说"以官方为准"、200 字内）
5. `POLICY_IMPORT_PROMPT` 政策导入结构化（只抽原文写了的，不补全不编造）
6. `POLICY_LOOKUP_PROMPT` 当地政策方向（未收录地区，用"方向"表述、金额不确定写"以当地官方为准"）

### 5.8 `app.py` — UI 入口

- **Gradio 6.x**，枫叶浅暖橙红主题（色板常量在文件头，改色改一处）。
- 资产 **base64 内嵌**（`_asset_b64`），跨环境无路径问题；背景图用 `#full-bg` img 层（z-index:-1）而非 CSS base64，避免膨胀。
- **4 个 Tab**：
  - ① 补贴材料预审：左对话右驾驶舱，`process_chat` 状态机。
  - ② 经营健康诊断：填表/一键摄影师示例 → 三指数。
  - ③ 经营合规问答：联网 + LLM → mock 兜底。
  - ④ 政策导入：原文 → 结构化 → 写库注册。
- **地区选择器**：`allow_custom_value=True`，可下拉切换（温州/杭州）或自由输入任意城市——**完全用户驱动，不预置城市**。
- **深色模式兼容**：CSS 用 `!important` 覆盖 Gradio 深色默认（近黑底/白字），强制暖底深棕字。
- 顶部 `region_dd.change` 切换地区 → 同步 profile + 立即重算驾驶舱。

---

## 六、关键算法速查

| 想做什么 | 调什么 |
|---------|--------|
| 一句描述 → 抽取字段 | `bp.extract_from_text(text, profile)` |
| 下一个要问的问题 | `bp.next_question(profile)` |
| 匹配政策（三态） | `rule_engine.match_policies(profile, region)` |
| 可直接申请的政策 | `rule_engine.matched_policies(profile, region)` |
| 材料清单 | `rule_engine.build_checklist(profile, region)` |
| 风险 | `rule_engine.assess_risk(profile)` |
| 综合摘要 | `rule_engine.summary(profile, region)` |
| 三指数 + 6 维向量 | `state_model.compute_indices(profile, region)` |
| 行动建议 | `state_model.build_recommendations(profile, indices)` |
| 实时搜当地政策 | `policy_searcher.search_and_format(region)` |
| LLM 调用（语义理解） | `api_client.chat() / generate()` |
| 渲染驾驶舱 | `app.render_cockpit(profile, region, indices, summ)` |

---

## 七、零白屏与降级设计

**核心铁律：核心 = 联网搜索当地政策（需网络）+ 规则判定资格。断网/受限时降级本地通用库 → 不白屏、不造假（保底，非核心）。LLM 是语义理解层（任意行业/搜索词/合规问答），非"可选增强"。**

| 场景 | 有 key | 无 key（LLM 不可用） |
|------|--------|--------|
| 材料预审 | LLM 语义抽取 + 规则匹配 + LLM 润色追问 | 句法抽取 + 规则匹配 + 规则问题（自带选项提示） |
| 经营诊断 | 规则三指数 | 规则三指数（同一结果） |
| 合规问答 | LLM + 联网 + 知识库 | 内置 COMPLIANCE_MOCK 知识库 + 联网 |
| 政策导入 | LLM 结构化 → 规则解析兜底 | 规则解析直接入库 |
| 未收录地区 | 实时搜索 + LLM 政策方向 | 实时搜索 → 失败回落 general 通用方向 |

**降级链顺序（都失败不回崩）**：LLM → 句法/规则兜底（零值枚举）→ mock/通用库。

---

## 七·五、2026-08-06 审查修复（P1-P6）

| 编号 | 问题 | 修复 |
|------|------|------|
| P1 | 演示脚本镜头1 声称"符合3项地区政策"但输入（毕业超5年）实际匹配 0 项 | 镜头1 输入改为"2022年毕业"（实测验证输出 3 项地区政策 + 72/3/中），数字均实测，非预编 |
| P2 | 同一摄影师案例身份冲突（镜头1"毕业超5年" vs do_prefill"2022"） | 统一为 2022 毕业；对话版与填表版现在都真实输出 72/3/中 |
| P3 | 杭州政策库脏数据 `[IMP-2] 11111` | 已删；`_write_policies_file` 加 `_policy_name_ok` 防护（长度≥4/非纯数字/非占位词），新导入+读回历史都过滤 |
| P4 | 材料预审对话路径不问关键非必填 → 地区匹配恒为 0 | `business_profile` 加 `OPTIONAL_ASK_KEYS=["grad_year","team_size"]` + `pending_ask`/`is_ask_complete`；process_chat 改用之，必填问完后继续问关键非必填 |
| P5 | `EXPLAIN_PROMPT` 死代码（定义未调用） | `render_report` 对 top 地区政策接入顾问式解读（有 key 时，失败静默降级纯规则） |
| P6 | README"三个场景"过时 | 改为"四个场景" |

另修复：region 句法模式③"我是[城市]做[行业]"（如"我是宁波做宠物殡葬的"→宁波），原缺口会错落回下拉默认温州。

---

## 九、部署指南

### 8.1 本地运行

```bash
cd demo
pip install -r requirements.txt
python app.py        # http://localhost:7860
```

Windows 用户可直接双击 `启动.bat`（自动装依赖 + 开浏览器）。

可选配置 AI 深度回答：

```bash
# Windows
set MODELSCOPE_API_KEY=ms-xxx
# Linux / Mac
export MODELSCOPE_API_KEY=ms-xxx
```

### 8.2 魔搭创空间（在线）

详见 `../部署创空间操作清单.md`。要点：

1. **新建空间**（严禁推进上个赛的 `qingfengyuqing/feng`），运行时 Gradio 选 **6.x**，免费 CPU，公开，MIT/Apache-2.0。
2. 本地 `git push modelscope master`（push 前 `git remote -v` 确认 URL 末尾是新空间名）。
3. 创空间「设置/Secrets」填 `MODELSCOPE_API_KEY`——**token 绝不进任何代码/README/commit**。
4. 验收：4 个 Tab 全跑通 + 摄影师示例健康 72/政策 3/风险中 + 深色模式文字可读。

### 8.3 GitHub 开源

- 仓库：`https://github.com/qingfengyu153781-star/fengdu-opc`（remote 名 `github`）。
- `.gitignore` 已隔离 `.backup/`、`__pycache__/`、`*.log`、`*.stackdump`。

---

## 十、扩展新地区

**方法一：政策导入（推荐，零代码）**
1. Tab ④ 填地区名 + 粘贴真实政策原文 → 入库（AI 结构化优先，规则解析兜底）。
2. 重启服务 → 地区下拉出现新地区。入库文件在 `policies/<code>.py`，`data_status` 标「导入数据·待核对」。
3. ⚠️ 入库后**人工核对**与官方原文一致（零造假原则）。

**方法二：手工模板（可控）**
1. 复制 `policies/region_template.py` → `policies/<code>.py`。
2. 用真实政策数据替换 `POLICIES`（**不要编造**），每项带 `source` + `source_url`。
3. 在 `policies/__init__.py` 的 `REGIONS` 注册。
4. 若地区名不在 `_CITY_PINYIN` 拼音表，`_slug()` 会生成 `custom_<拼音>` 兜底 code。

**方法三：任意城市（零数据，演示即用）**
用户在地区框直接输入任意城市 → 自动走「实时搜索 + general 通用方向」路径，无需入库即可演示。

---

## 十一、测试与验收

### 10.1 验收基准（与 PPT 一致）

摄影师示例一键带入（Tab ②「🍁 带入摄影师示例」）应输出：**健康 72 / 政策机会 3 / 风险中**，材料清单含「营业执照 已备」。

### 10.2 手测清单

| 项 | 动作 | 期望 |
|----|------|------|
| ①材料预审 | "我是温州的个体户摄影师，开了2年，月入3万" | 逐项追问 → 材料清单 + 三指数 |
| ①追问兜底 | 被问社保时答"没交" | 封闭选项兜底识别为"无"，进度前进 |
| ②诊断 | 填表/摄影师示例 | 三指数驾驶舱 + 报告 |
| ③合规问答 | "小规模纳税人月销售额多少免征增值税" | 带来源回答（无 key 走 mock） |
| ④政策导入 | 粘贴真实政策原文 | 入库 + 地区下拉出现新地区 |
| 联网搜索 | "我是重庆的" | 实时搜索重庆政策（带来源 URL；失败回落通用库） |
| 深色模式 | 系统开深色 | 文字可读，非白字黑底 |
| 零白屏 | 不配 key 全部走一遍 | 永不白屏 |

### 10.3 回归注意

- 改 `policies/*.py` 后**重启服务**（地区注册表启动时加载）。
- 改 `FIELDS` 后检查 `EXTRACT_PROMPT` 字段清单、摄影师 prefill、`_CITY_PINYIN` 是否同步。
- 政策库里改金额/资格 → 同时核对 `COMPLIANCE_KNOWLEDGE` 与温州操作指南口径（信息同步防漂移铁律）。

---

## 十二、合规边界

| 红线 | 规则 |
|------|------|
| 不替代专业判断 | 所有输出带「辅助参考，不替代专业机构/金融机构最终判断」 |
| 不给确定结论 | 禁止确定性投资/贷款审批/保险赔付结论 |
| 零造假 | 政策只收录真实原文，未收录地区用"方向"表述 +「以当地官方为准」 |
| 数据可溯源 | 每条政策带 `source` + `source_url` |
| 用户数据 | 不收集真实个人信息，Demo 使用模拟数据（摄影师为示例） |
| 知识产权 | 政策库为公开政策文件整理（财政部/税务总局公告、浙江政务服务网等），可溯源 |

---

## 十三、已知限制与后续（诚实边界）

- **政策会变**：手工维护的库有更新滞后风险。长期方向：`policy_updater` 自动爬取更新（待实现）。
- **规则覆盖率**：`_check_condition` 已覆盖主流条件类，但**未识别的条件返回 unknown**，不猜。复赛可补自动抽取规则结构（研究笔记 §四-4 提到的待验证假设）。
- **实时搜索不稳定**：创空间可能限制外网，搜索失败属正常降级，不白屏但信息靠通用库。
- **跨行业适配**：餐饮/建筑/文创只有框架级假设，未实测。
- **无真实用户数据**：只验证了"申请流程本人走通"，未验证"别人用更快"。

---

*开发文档 v1.0 · 与代码同步：2026-08-06*
