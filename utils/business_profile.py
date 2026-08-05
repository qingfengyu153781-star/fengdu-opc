# -*- coding: utf-8 -*-
"""经营信息字段模型 + 追问状态机（主动询问核心）。

设计：19 个经营信息字段。用户往往说不清自己情况（"我是什么类型的企业""我算不算科技人员"），
所以 Agent 不依赖一次说清——缺哪些字段就逐项问，问全才进入匹配。这就是"主动询问"。

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


# ---- 关键词规则抽取（确定性，不依赖 LLM） ----
# (字段 key, 正则, 提取函数)
_SPECIAL_PARSERS = {
    "region": [
        (r"温州|wenzhou", lambda m: "温州"),
        (r"杭州|hangzhou", lambda m: "杭州"),
        (r"北京|beijing", lambda m: "北京"),
        (r"上海|shanghai", lambda m: "上海"),
        (r"广州|guangzhou", lambda m: "广州"),
        (r"深圳|shenzhen", lambda m: "深圳"),
        (r"福建|福建省|fujian", lambda m: "福建"),
        (r"南京|nanjing", lambda m: "南京"),
        (r"成都|chengdu", lambda m: "成都"),
        (r"武汉|wuhan", lambda m: "武汉"),
        (r"重庆|chongqing", lambda m: "重庆"),
        (r"西安|xian|西安", lambda m: "西安"),
        (r"苏州|suzhou", lambda m: "苏州"),
        # 通用兜底：在XX(注册/经营/创业…) → 提取城市名
        (r"在([一-龥]{2,8}?)(?:注册|经营|开(?:了|个|的)?|创业|做生意|发展|上班)", lambda m: m.group(1)),
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
    "industry": [
        (r"摄影|拍照|摄像|剪辑", lambda m: "摄影"),
        (r"软件|程序|开发|编程|AI|人工智能", lambda m: "软件开发"),
        (r"餐饮|外卖|饭店", lambda m: "餐饮"),
        (r"咨询", lambda m: "咨询"),
        (r"设计|平面|视觉", lambda m: "设计"),
        (r"电商|淘宝|拼多多|网店", lambda m: "电商"),
    ],
}

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
    """从一句话里用关键词规则抽取单个字段值（确定性，用于 mock/兜底）。"""
    text = text.strip()
    # 特化规则（枚举型字段）
    if key in _SPECIAL_PARSERS:
        for pattern, fn in _SPECIAL_PARSERS[key]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return fn(m)
    # 数字型字段
    if key in _NUMBER_PARSERS:
        for pattern, fn in _NUMBER_PARSERS[key]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return fn(m)
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
    """从用户一句话抽取多个字段值，合并进 profile（关键词规则版）。

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


def next_question(profile: dict) -> str | None:
    """返回下一个要问的问题（缺失字段的第一个），全部问完返回 None。"""
    missing = missing_fields(profile)
    if not missing:
        return None
    return missing[0]["ask"]


def is_complete(profile: dict) -> bool:
    """全部必填字段是否齐全。"""
    return len(missing_fields(profile)) == 0


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
