# -*- coding: utf-8 -*-
"""经营信息字段模型 + 追问状态机（主动询问核心）。

设计：18 个经营信息字段。用户往往说不清自己情况（"我是什么类型的企业""我算不算科技人员"），
所以 Agent 不依赖一次说清——缺哪些字段就逐项问，问全才进入匹配。这就是"主动询问"。

抽取架构（v2，零值枚举）：**LLM 理解为主，规则只做兜底**。
- 有 MODELSCOPE_API_KEY 时：app.llm_extract_profile 用模型理解任意表达（用户说什么就抽什么）。
- 无 key / LLM 失败时：本模块只靠「纯句法模式 + 封闭选项 + 数字正则」兜底，**不预置任何
  城市/行业表**——地区/行业是开放值，靠"在XX经营/注册""我(做|是|开)XXX"这类句法结构抓原文，
  不做硬编码枚举（硬对应穷举删干净了）。

优先级：region 最高（决定政策路由），其次是材料预审关键字段（注册类型/社保/学历/毕业年）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# ---- 字段定义 ----
# key / label(中文) / required / priority(越小越先问) / ask(追问问题) / options(可选值)
FIELDS = [
    {"key": "region",          "label": "所在城市/地区", "required": True,  "priority": 1,
     "ask": "你在哪个城市注册/经营？（不同地区政策不同）"},
    {"key": "reg_type",        "label": "注册类型",      "required": True,  "priority": 2,
     "ask": "你是哪种注册类型？（答：个体工商户 / 一人有限责任公司 / 其他）",
     "options": ["个体工商户", "一人有限责任公司", "其他"]},
    {"key": "social_security", "label": "社保",          "required": True,  "priority": 3,
     "ask": "你有缴纳社保吗？（答：有 / 无，灵活就业社保也算）",
     "options": ["有", "无"]},
    {"key": "education",       "label": "学历",          "required": True,  "priority": 4,
     "ask": "你的最高学历是什么？（答：本科 / 专科 / 研究生 / 其他）",
     "options": ["本科", "专科", "研究生", "其他"]},
    {"key": "duration",        "label": "经营时长",      "required": True,  "priority": 5,
     "ask": "公司/个体户开了多久了？（答：1年 / 2年）"},
    {"key": "grad_year",       "label": "毕业年份",      "required": False, "priority": 6,
     "ask": "哪一年毕业的？如：2022（判断是否在『毕业 5 年内』政策窗口）"},
    {"key": "revenue",         "label": "月营收",        "required": True,  "priority": 7,
     "ask": "平均每月营收大概多少？（答：3万 / 8000）"},
    {"key": "industry",        "label": "行业",          "required": True,  "priority": 8,
     "ask": "你主要从事什么行业？（如：软件开发/摄影/餐饮/咨询）"},
    {"key": "cost",            "label": "月成本",        "required": False, "priority": 9,
     "ask": "每月固定成本/支出大概多少？（不知道可以跳过）"},
    {"key": "cash_buffer",     "label": "现金流缓冲",    "required": False, "priority": 10,
     "ask": "手上现金大概能撑几个月？"},
    {"key": "client_concentration", "label": "客户集中度", "required": False, "priority": 11,
     "ask": "有没有某个客户占收入很大比例？大概百分之多少？"},
    {"key": "team_size",       "label": "团队规模",      "required": False, "priority": 12,
     "ask": "除了你还有几个人？（招兼职/实习生也算）"},
    {"key": "corp_account",    "label": "对公账户",      "required": False, "priority": 13,
     "ask": "有开银行对公账户吗？（答：有 / 无）",
     "options": ["有", "无"]},
    {"key": "biz_scope_ai",    "label": "经营范围含AI/软件", "required": False, "priority": 14,
     "ask": "经营范围里有『软件开发』『人工智能应用』这类吗？（答：有 / 无）",
     "options": ["有", "无"]},
    {"key": "order_cycle",     "label": "订单周期",      "required": False, "priority": 15,
     "ask": "一般一单生意周期多长？（如：1-3 个月/单）"},
    {"key": "continuity",      "label": "经营连续性",    "required": False, "priority": 16,
     "ask": "经营有没有中断过？"},
    {"key": "risk_items",      "label": "风险项",        "required": False, "priority": 17,
     "ask": "有什么经营上的担心或风险点吗？"},
    {"key": "has_materials",   "label": "已有材料",      "required": False, "priority": 18,
     "ask": "目前手上已经有哪些材料？（如营业执照/身份证）"},
]

FIELD_KEYS = [f["key"] for f in FIELDS]
REQUIRED_KEYS = [f["key"] for f in FIELDS if f["required"]]


def empty_profile() -> dict:
    """新建空 profile（全部字段为空）。"""
    return {k: "" for k in FIELD_KEYS}


# ---- 兜底抽取规则（零值枚举，LLM 不可用时才走） ----
# (字段 key, 正则, 提取函数)
# 原则：删掉一切硬编码值表（不预置城市、不预置行业关键词）。
# - region / industry：开放值，只靠句法模式（"在XX经营/注册""我(做|是|开)XXX"）抓用户原文
# - reg_type / education / social_security / biz_scope_ai / corp_account：
#   封闭选项字段，问句里已定义选项（"答：有/无"），按选项匹配不算穷举
# - 数字字段走 _NUMBER_PARSERS（结构化数据，正则天然合适）
_SPECIAL_PARSERS = {
    "region": [
        # 句法模式①："在XX(注册|经营|创业|做生意|上班…)" → XX 为地区（地点+经营动作结构）
        (r"在([一-龥]{2,8}?)(?:注册|经营|开(?:了|个|的)?|创业|做生意|发展|上班|做|搞)",
         lambda m: m.group(1)),
        # 句法模式②："我是温州个体工商户" → 注册类型标记前的词为地区（地点+注册类型结构）。
        # 守卫：若捕获词含动作动词（"我是做摄影的个体户"）→ 拒绝，交给下拉兜底，绝不猜错地区
        (r"我(?:是|在)?([一-龥]{2,8}?)(?:个体工商户|个体户|一人公司|一人有限责任公司|有限责任公司|有限公司|公司)",
         lambda m: m.group(1) if not any(v in m.group(1) for v in ("做", "搞", "从事", "干", "开", "经营")) else ""),
        # 句法模式③："我是宁波做宠物殡葬的" → 动词前的词为地区（地点+行业结构）。
        # "做/搞/从事"前无字（"我是做摄影的"）→ 不匹配，绝不猜错
        (r"我(?:是|在)?([一-龥]{2,8}?)(?:做|搞|从事|干|开|经营)([一-龥]{2,10})",
         lambda m: m.group(1)),
    ],
    "reg_type": [
        (r"个体工商户|个体户|个体", lambda m: "个体工商户"),
        (r"一人有限责任公司|一人公司|有限责任公司|有限公司|公司", lambda m: "一人有限责任公司"),
        (r"合伙", lambda m: "其他"),
    ],
    "social_security": [
        (r"没(有)?社保|无社保|不交社保|没交(社保)?|未缴|社保.*(没|无|不)", lambda m: "无"),
        (r"没|无|不交|不缴|未缴|没交|还没有|没有", lambda m: "无"),
        (r"有社保|缴(了|纳|着)?|交(了|着|过)?(社保)?|在交|在缴|已缴", lambda m: "有"),
        (r"有|交|缴", lambda m: "有"),  # 注意不含'是'：'我是XX'里的'是'会误判为有社保
    ],
    "education": [
        (r"研究生|硕士|博士", lambda m: "研究生"),
        (r"专科|大专", lambda m: "专科"),
        (r"本科|大学本科|大学|学士", lambda m: "本科"),
        (r"高中|初中|其他", lambda m: "其他"),
    ],
    "biz_scope_ai": [
        (r"经营范围.*(软件|AI|人工智能)", lambda m: "有"),
    ],
    "corp_account": [
        (r"有.*对公|对公.*有", lambda m: "有"),
        (r"没(有)?对公|对公.*没", lambda m: "无"),
    ],
    "has_materials": [
        # 材料列表：识别"有/已有/已备 X"结构（带"没/无"守卫防误抓"没有营业执照"）
        # 一次抓一个材料（常见演示：用户一句话说"有营业执照"），多处靠后续追问/补充
        (r"(?<!没)(?<!无)(?:已有|已备|准备好了|手里|手上|目前有|有).{0,8}?(营业执照|身份证|毕业证|学位证|公章|发票|社保缴纳记录|社保缴费证明|劳动合同|商业计划书|软著|软件产品登记证书|软件著作权证书|章程|对公账户|银行开户许可证|经营场所证明)",
         lambda m: m.group(1)),
        # 纯罗列式："营业执照和身份证都有" / "材料有营业执照"
        (r"(?:材料|证件|资料).{0,4}?(?:有|已有)(营业执照|身份证|毕业证|公章)", lambda m: m.group(1)),
    ],
    # 注意：industry 无硬编码关键词表——开放值，统一走 extract_industry_free 纯句法模式
}


def extract_industry_free(text: str) -> str:
    """行业自由文本识别（纯句法模式，零值枚举）。

    行业是开放值，与政策搜索同哲学：不预置任何行业表，用户说什么行业就识别什么。
    只靠句法模式"我(做|从事|搞|是|干|开|经营)XXX"，把 XXX 原文提取为行业。
    任何行业（金融/教培/宠物殡葬/元宇宙…）都能识别，无一例外——这是句法，不是穷举。
    """
    t = (text or "").strip()
    if not t:
        return ""
    import re
    # 模式1：我(做|从事|搞|干|开|经营|主做|主营)XXX —— 动词后接行业
    # 注意：不用"是"当动词（太泛，会误抓"是做教培"的"做"）；非贪婪但至少抓 2 字
    m = re.search(r"(?:我|本人)?(?:做|从事|搞|干|开|经营|主做|主营)([一-龥]{2,8})", t)
    if m:
        ind = m.group(1).strip()
        # 去掉"的/了/行业/公司"等词尾
        ind = re.sub(r"(的|了|行业|类|方面|生意|公司|个体户|工作室|店|工作|项目|这一行)$", "", ind)
        if ind and len(ind) >= 2:
            return ind
    # 模式2：我是做XXX / 我是搞XXX（"做/搞"在"是"后，单独匹配）
    m2 = re.search(r"是(做|搞|从事|干)([一-龥]{2,8})", t)
    if m2:
        return m2.group(2).strip()
    # 模式3：主营/从事/做 XXX 行业
    m3 = re.search(r"(?:从事|主营|做|搞)([一-龥]{2,8})行业", t)
    if m3:
        return m3.group(1).strip()
    # 模式4：无动词——"我XXX的" / "我直播带货"（省略"做"的行业表达）
    # 例："我直播带货的"→直播带货，"开奶茶店的"→奶茶店
    # 约束：不以"是"开头（排除"我是温州个体户"），行业后接"的/店/行业/类"或行尾
    m4 = re.search(r"(?:我|本人)?(开|做|搞|干)([一-龥]{2,10}?)(?:的|店|行业|类)?$", t)
    if m4 and m4.group(2):
        ind = m4.group(2).strip()
        ind = re.sub(r"(的|了|行业|类|方面|生意|公司|个体户|工作室|店|工作|项目|这一行)$", "", ind)
        if ind and len(ind) >= 2:
            return ind
    # 模式5：纯"我XXX的"（无动词）
    # "我是个体户摄影师"→个体户是注册类型，摄影师是行业 → 取"个体户/个体工商户"后部分
    m5 = re.search(r"我(?:是)?([一-龥]{2,10}?)(?:的|行业|类)$", t)
    if m5 and m5.group(1):
        ind = m5.group(1).strip()
        # 去掉注册类型/地区前缀（个体户/个体工商户/一人公司），取剩余为行业
        ind = re.sub(r"^(个体工商户|个体户|一人公司|一人有限责任公司|有限公司|公司)", "", ind)
        # 若是纯注册类型（无行业），返回空（注册类型词是封闭选项，不枚举地区）
        if ind and len(ind) >= 2 and not any(k in ind for k in ("个体户", "公司")):
            return ind
    return ""


_CN_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(s: str) -> int:
    """中文数字转整数（支持 一~九十九）。"""
    s = (s or "").strip()
    if "十" in s:
        if s == "十":
            return 10
        left, _, right = s.partition("十")
        tens = _CN_DIGITS.get(left, 1)
        ones = _CN_DIGITS.get(right, 0)
        return tens * 10 + ones
    return _CN_DIGITS.get(s, 0)


def _cn_to_num_text(s: str) -> str:
    """中文数字→数字字符串（支持 一~九千九百九十九，如'八千'→'8000'）。"""
    s = (s or "").strip()
    if not s:
        return s
    # 处理"万"级
    if "万" in s:
        head, _, tail = s.partition("万")
        base = _cn_to_int(head) * 10000 if head else 10000
        if tail:
            base += _cn_to_int(tail)
        return str(base)
    # 千/百
    total, cur = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            cur = _CN_DIGITS[ch]
        elif ch == "千":
            total += (cur or 1) * 1000
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
    total += cur
    return str(total) if total else s


_NUMBER_PARSERS = {
    "revenue": [
        (r"([\d.]+)\s*(万|w|W)", lambda m: f"{m.group(1)}万/月"),
        (r"([\d.]+)\s*万", lambda m: f"{m.group(1)}万/月"),
        (r"([一二两三四五六七八九十]+)\s*万", lambda m: f"{_cn_to_int(m.group(1))}万/月"),
        # 带前缀限定的纯数字（月入/收入/营收 + 数字），避免误抓"开了1年"的1
        (r"(?:月入|月收入|收入|营收|月赚|赚)\s*(\d+(?:\.\d+)?)", lambda m: f"{m.group(1)}元/月"),
        (r"(?:月入|月收入|收入|营收|月赚|赚)\s*([一二两三四五六七八九十百千]+)(?!万)", lambda m: f"{_cn_to_num_text(m.group(1))}元/月"),
    ],
    "duration": [
        (r"([\d.]+)\s*年", lambda m: f"{m.group(1)}年"),
        (r"([\d.]+)\s*个月", lambda m: f"{m.group(1)}个月"),
        (r"([一二两三四五六七八九十]+)\s*年", lambda m: f"{_cn_to_int(m.group(1))}年"),
        (r"([一二两三四五六七八九十]+)\s*个月", lambda m: f"{_cn_to_int(m.group(1))}个月"),
        # 半年/半年左右 → 6个月
        (r"半\s*年", lambda m: "6个月"),
    ],
    "cash_buffer": [
        (r"(?:能撑|撑|够撑|缓冲|现金流|现金|手上).{0,4}?([\d.]+)\s*个月", lambda m: f"{m.group(1)}个月"),
        (r"([\d.]+)\s*个月.*(缓冲|现金流|撑)", lambda m: f"{m.group(1)}个月"),
        (r"(?:能撑|撑|够撑|缓冲|现金流|现金|手上).{0,4}?([一二两三四五六七八九十]+)\s*个月", lambda m: f"{_cn_to_int(m.group(1))}个月"),
        (r"(?:能撑|撑|够撑|缓冲|现金流|现金|手上).{0,4}?半\s*年", lambda m: "6个月"),
    ],
    "grad_year": [
        (r"(20\d{2})年?毕业", lambda m: m.group(1)),
        (r"毕业.*(20\d{2})", lambda m: m.group(1)),
        (r"(?<!\d)(20\d{2})(?!\d)", lambda m: m.group(1)),
    ],
    "team_size": [
        (r"([\d.]+)\s*(个|名)?人|就我一个人|就我", lambda m: m.group(1) if m.group(1) else "1"),
    ],
    "client_concentration": [
        (r"单?客户.*?([\d.]+)%|([\d.]+)%.*(客户|一个|单一)", lambda m: f"单客户{m.group(1) or m.group(2)}%"),
    ],
    "order_cycle": [
        (r"([\d.]+)\s*-\s*([\d.]+)\s*个月", lambda m: f"{m.group(1)}-{m.group(2)}个月/单"),
        (r"(?:订单|一单|单笔|周期|客单).{0,6}?([\d.]+)\s*个月", lambda m: f"{m.group(1)}个月/单"),
        (r"([\d.]+)\s*个月/单|([\d.]+)\s*个月一单", lambda m: f"{m.group(1) or m.group(2)}个月/单"),
    ],
}


def extract_field_value(text: str, key: str) -> str:
    """从一句话里抽取单个字段值（确定性兜底，无 key / LLM 失败时用，零值枚举）。"""
    text = text.strip()
    # 封闭选项 / 地区句法模式
    if key in _SPECIAL_PARSERS:
        for pattern, fn in _SPECIAL_PARSERS[key]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                v = fn(m)
                if v:  # 空结果（守卫拒绝，如"我是做摄影的个体户"）→ 继续下一个模式，不猜
                    return v
    # 数字型字段（结构化数据，正则天然合适）
    if key in _NUMBER_PARSERS:
        for pattern, fn in _NUMBER_PARSERS[key]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return fn(m)
    # 行业自由文本（纯句法模式，零值枚举）：行业关键词表已删除，统一走这里
    if key == "industry":
        v = extract_industry_free(text)
        if v:
            return v
    return ""


def extract_loose_number(text: str, key: str) -> str:
    """宽松数字兜底：当前字段抽不到时，从回答里提取第一个数字（含中文数字）。

    仅用于 process_chat 追问兜底（此时用户大概率在直接回答该数字字段）。
    - revenue: 无单位按"元/月"（如 8000 / 八千 → 8000元/月）
    - duration: 无单位按"年"（如 答"2" → 2年）
    - cash_buffer/order_cycle/team_size: 无单位按原样
    """
    t = (text or "").strip()
    if not t:
        return ""
    # 先试精确正则（覆盖"半年""18个月"等已支持形式）
    v = extract_field_value(t, key)
    if v:
        return v
    # 阿拉伯数字
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if m:
        n = m.group(1)
        if key == "revenue":
            return f"{n}元/月"
        if key == "duration":
            return f"{n}年"
        return n
    # 中文数字
    cn = re.search(r"([一二两三四五六七八九十百千]+)", t)
    if cn:
        num = _cn_to_num_text(cn.group(1))
        if key == "revenue":
            return f"{num}元/月"
        if key == "duration":
            return f"{num}年"
        return num
    return ""


def parse_yes_no(text: str) -> str:
    """通用有/无解析：回答'有/没有/交了/没交'等 → '有'/'无'。供追问兜底用。"""
    t = (text or "").strip()
    if re.search(r"没|无|不交|不缴|未缴|没有|否", t):
        return "无"
    if re.search(r"有|交|缴|是", t):
        return "有"
    return ""


def extract_from_text(text: str, profile: dict | None = None) -> dict:
    """从用户一句话抽取多个字段值，合并进 profile（句法模式 + 封闭选项兜底版，零值枚举）。

    Returns: {field_key: value} 只含本次识别出的字段。
    """
    profile = profile or empty_profile()
    result: dict[str, str] = {}
    for key in FIELD_KEYS:
        val = extract_field_value(text, key)
        if val and not profile.get(key):
            result[key] = val
    return result


def parse_llm_json(raw: str) -> dict:
    """解析 LLM 结构化抽取输出（JSON）→ 字段值 dict。

    容错：去掉 markdown 代码块标记、截取 { } 之间内容、忽略无法解析。
    """
    if not raw:
        return {}
    # 去 ```json ... ```
    text = re.sub(r"```(?:json)?", "", raw).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    import json
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # 只保留已知字段
    out = {}
    for k, v in data.items():
        if k in FIELD_KEYS and isinstance(v, (str, int, float, bool)) and str(v).strip():
            out[k] = str(v).strip()
    return out


# ---- 追问状态机 ----
def missing_fields(profile: dict) -> list[dict]:
    """返回缺失的必填字段（按 priority 排序）。"""
    missing = []
    for f in sorted([x for x in FIELDS if x["required"]], key=lambda x: x["priority"]):
        if not profile.get(f["key"]):
            missing.append(f)
    return missing


# 非必填但直接影响政策匹配的关键字段（P4 修复：材料预审必填问完后继续问这些，
# 否则温州 S1/S2/S9（毕业5年）S4（招人）等永远判 unknown → 地区匹配恒为 0）
OPTIONAL_ASK_KEYS = ["grad_year", "team_size"]


def pending_ask(profile: dict) -> list[dict]:
    """追问源：必填缺失 + 关键非必填未填（按 priority 排序）。

    材料预审的"完整"= 必填齐 + 关键非必填齐，保证匹配真实可判（不因缺字段恒 unknown）。
    """
    missing = missing_fields(profile)
    for f in sorted(FIELDS, key=lambda x: x["priority"]):
        if f["key"] in OPTIONAL_ASK_KEYS and not profile.get(f["key"]):
            missing.append(f)
    return missing


def next_question(profile: dict) -> str | None:
    """返回下一个要问的问题（缺失字段的第一个），全部问完返回 None。"""
    missing = pending_ask(profile)
    if not missing:
        return None
    return missing[0]["ask"]


def is_complete(profile: dict) -> bool:
    """全部必填字段是否齐全。"""
    return len(missing_fields(profile)) == 0


def is_ask_complete(profile: dict) -> bool:
    """追问是否全完成（必填齐 + 关键非必填齐）。

    诊断填表路径只用 is_complete（不强制非必填）；材料预审对话路径用这个，
    保证"毕业年份/团队规模"这两个决定政策匹配的字段不缺失。
    """
    if not is_complete(profile):
        return False
    return all(profile.get(k) for k in OPTIONAL_ASK_KEYS)


def summarize(profile: dict) -> str:
    """把 profile 转成可读摘要（供状态抽取展示）。"""
    if not profile:
        return ""
    lines = []
    for f in FIELDS:
        v = profile.get(f["key"])
        if v:
            lines.append(f"{f['label']}：{v}")
    return "；".join(lines)


def to_llm_context(profile: dict) -> str:
    """把已填字段转成给 LLM 的上下文描述。"""
    return summarize(profile) or "（用户尚未提供信息）"
