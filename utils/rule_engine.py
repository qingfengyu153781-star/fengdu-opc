# -*- coding: utf-8 -*-
"""规则引擎：政策资格匹配 + 材料清单 + 风险评估（确定性，按地区路由）。

设计原则（呼应研究笔记「为什么用大模型+规则库」）：
- 政策是高度结构化的（资格/材料/金额），但表述五花八门
- 纯向量检索能"找到相关段落"，但不能"判断你符不符合资格"
- 所以政策拆成「结构化规则 + 原文引用」：规则负责推理，原文负责溯源
- 规则可能误判，但原文永远可以核对 → 所有输出带来源

匹配结果三态：
- match   ：条件全部满足，可申请
- no      ：存在不满足条件（阻塞），标注原因 + 替代路径
- unknown ：缺信息，需追问确认（驱动多轮主动询问）

当前年份（毕业窗口等判定用）：2026。政策以官方最新公告为准（见 policy_updater）。
"""
from __future__ import annotations

import re
from datetime import datetime

# 毕业窗口等判定用当前年份。动态取，避免硬编码过一年全部失效（2026 铁律：政策以官方最新公告为准）
CURRENT_YEAR = datetime.now().year

from policies import all_policies, region_info

# 政策库经人工核实的地区 code（数据可作正式申请依据）。
# 未在其中的地区（自助导入/占位）→ 地区政策仅作"待核实参考"，不纳入政策机会指数与材料清单。
VERIFIED_REGIONS = {"wenzhou"}


def _is_verified(region: str) -> bool:
    return region in VERIFIED_REGIONS


# ---------- 工具函数 ----------
def _to_num(text) -> float | None:
    """从文本提取第一个数字。"""
    if text is None:
        return None
    m = re.search(r"([\d.]+)", str(text))
    return float(m.group(1)) if m else None


def _duration_years(duration: str) -> float | None:
    """把经营时长('2年'/'18个月')转成年数。"""
    if not duration:
        return None
    n = _to_num(duration)
    if n is None:
        return None
    if "年" in str(duration):
        return n
    if "个月" in str(duration) or "月" in str(duration):
        return n / 12
    return None


def _duration_months(duration: str) -> float | None:
    """把经营时长('2年'/'18个月')转成月数。"""
    if not duration:
        return None
    n = _to_num(duration)
    if n is None:
        return None
    if "年" in str(duration):
        return n * 12
    if "个月" in str(duration) or "月" in str(duration):
        return n
    return None


def _revenue_wan(rev_text) -> float | None:
    """把月营收文本统一转成「万元/月」口径（元/万混用会判错资格，F11 修复）。

    抽取端会把「3万」存成 '3万/月'、把「8000」存成 '8000元/月'（business_profile 规则），
    单位不一致导致 _to_num 拿到 3 与 8000 两个数量级 → 碰「应纳税所得额/月销售额」上限时错判。
    此函数归一为万元：'3万/月'→3.0，'8000元/月'→0.8，'2.5万'→2.5。
    """
    if not rev_text:
        return None
    s = str(rev_text).strip()
    m = re.search(r"([\d.]+)", s)
    if not m:
        return None
    n = float(m.group(1))
    if "万" in s:
        return n          # 已是万元
    if "元" in s or "块" in s:
        return n / 10000  # 元 → 万元
    # 无单位：抽取端默认按「元/月」记录（如月入8000 → 8000元/月），也按元折算
    return n / 10000


# ---------- 条件判定 ----------
def _check_condition(cond: str, profile: dict) -> tuple[str, str]:
    """判定单条资格条件。

    Returns:
        (status, reason)  status ∈ {'match','no','unknown'}
    """
    p = profile
    cond = cond.strip()

    # --- 学历 ---
    if "本科及以上" in cond or "全日制本科及以上" in cond:
        edu = p.get("education")
        if not edu:
            return "unknown", "需确认最高学历"
        if edu in ("本科", "研究生", "硕士", "博士"):
            return "match", f"学历（{edu}）满足"
        return "no", f"学历（{edu}）不满足本科及以上要求"

    if "毕业" in cond and ("年内" in cond or "年以内" in cond or "高校毕业生" in cond):
        # 毕业 5 年内高校毕业生 / 毕业 X 年内
        grad = p.get("grad_year")
        if not grad:
            return "unknown", "需确认毕业年份（判断是否在窗口内）"
        try:
            years = CURRENT_YEAR - int(re.sub(r"\D", "", str(grad)))
        except Exception:
            return "unknown", "毕业年份无法解析"
        if years <= 5:
            return "match", f"毕业{years}年，在5年窗口内"
        return "no", f"毕业已{years}年，超出5年窗口"

    if "在校大学生" in cond:
        return "unknown", "需确认当前是否在校"

    # --- 地区 ---
    if "温州" in cond:
        r = p.get("region")
        if not r:
            return "unknown", "需确认所在城市"
        if "温州" in r:
            return "match", "注册/经营地在温州"
        return "no", f"所在地区（{r}）非温州"

    # --- 注册类型 ---
    if "独立法人" in cond:
        rt = p.get("reg_type")
        if not rt:
            return "unknown", "需确认注册类型"
        if rt == "一人有限责任公司":
            return "match", f"注册类型（{rt}）为独立法人"
        return "no", f"注册类型（{rt}）非独立法人企业（如需要可考虑公司化）"

    if ("OPC" in cond or "一人公司" in cond or "一人有限责任" in cond) and (
        "注册" in cond or "设立" in cond or "开办" in cond
    ):
        rt = p.get("reg_type")
        if not rt:
            return "unknown", "需确认注册类型"
        if "一人" in rt or "个体" in rt:
            return "match", f"注册类型（{rt}）符合"
        return "no", f"注册类型（{rt}）不适用"

    if "注册" in cond and "公司" in cond:
        rt = p.get("reg_type")
        if not rt:
            return "unknown", "需确认注册类型"
        return "match", f"已注册（{rt}）"

    # --- 正常经营 / 时长 ---
    if "正常经营" in cond:
        if not p.get("duration"):
            return "unknown", "需确认经营时长"
        return "match", f"经营中（{p.get('duration')}）"

    if "年以上" in cond:
        m = re.search(r"(\d+)\s*年", cond)
        n = int(m.group(1)) if m else 1
        y = _duration_years(p.get("duration") or "")
        if y is None:
            return "unknown", "需确认经营时长"
        if y >= n:
            return "match", f"经营约{y:.1f}年，满足{n}年以上"
        return "no", f"经营约{y:.1f}年，不足{n}年"

    if ("满" in cond and "个月" in cond) or ("成立" in cond and "个月" in cond):
        # 部分区要求公司成立满 3 个月（S2 区级创业补贴）
        m = re.search(r"满\s*(\d+)\s*个月", cond)
        n = int(m.group(1)) if m else 3
        months = _duration_months(p.get("duration") or "")
        if months is None:
            return "unknown", "需确认经营时长（判断是否满成立期限）"
        if months >= n:
            return "match", f"已成立约{months:.0f}个月，满足满{n}个月要求"
        return "no", f"已成立约{months:.0f}个月，不足{n}个月"

    # --- 社保 ---
    if "缴纳社保" in cond or "缴社保" in cond:
        ss = p.get("social_security")
        if not ss:
            return "unknown", "需确认社保缴纳情况"
        if ss in ("有", "是", "已缴"):
            return "match", "已缴纳社保"
        return "no", "未缴纳社保（此项为阻塞条件）"

    # --- 招用员工 ---
    if "招用" in cond:
        ts = p.get("team_size")
        ss = p.get("social_security")
        if not ts:
            return "unknown", "需确认团队规模"
        if _to_num(ts) is not None and _to_num(ts) >= 1 and ss == "有":
            return "match", f"团队{ts}人且缴纳社保"
        if _to_num(ts) is not None and _to_num(ts) >= 1:
            return "unknown", "需确认为员工缴纳社保（兼职/实习也需缴）"
        return "no", "未招用员工"

    # --- 营收 / 应纳税所得额 ---
    if "应纳税所得额不超过" in cond:
        m = re.search(r"不超过\s*([\d.]+)\s*万", cond)
        cap = float(m.group(1)) if m else 300.0
        rev = p.get("revenue")
        if not rev:
            return "unknown", "需确认月营收"
        rv = _revenue_wan(rev)  # 统一万元口径（F11：避免 元/万 混用判错）
        if rv is None:
            return "unknown", "营收无法解析"
        annual = rv * 12
        if annual <= cap:
            return "match", f"年营收约{annual:.0f}万 ≤ {cap:.0f}万"
        return "no", f"年营收约{annual:.0f}万 超过 {cap:.0f}万"

    if "月销售额不超过" in cond:
        m = re.search(r"不超过\s*([\d.]+)\s*万", cond)
        cap = float(m.group(1)) if m else 10.0
        rev = p.get("revenue")
        if not rev:
            return "unknown", "需确认月营收"
        rv = _revenue_wan(rev)  # 统一万元口径
        if rv is None:
            return "unknown", "营收无法解析"
        if rv <= cap:
            return "match", f"月营收{rv:.1f}万 ≤ {cap:.0f}万"
        return "no", f"月营收{rv:.1f}万 超过 {cap:.0f}万"

    if "人数不超过" in cond:
        m = re.search(r"不超过\s*([\d.]+)\s*人", cond)
        cap = int(m.group(1)) if m else 300
        ts = p.get("team_size")
        if not ts:
            # 一人公司/个体户从业人数远低于上限，默认满足（以申报数据为准）
            return "match", "一人公司人数远低于上限（以申报数据为准）"
        tv = _to_num(ts)
        if tv is not None and tv <= cap:
            return "match", f"团队{tv:.0f}人 ≤ {cap}人"
        if tv is not None:
            return "no", f"团队{tv:.0f}人 超过 {cap}人"
        return "unknown", "需确认团队人数"

    if "资产总额不超过" in cond:
        return "match", "一人公司单体资产规模远低于限额（以申报数据为准）"

    if "从事国家非限制和禁止行业" in cond:
        return "match", "一般经营行业符合（除非特殊限制行业）"

    # --- 个体工商户 / 小型微利 ---
    if cond == "个体工商户" or cond == "个体工商户（月销售额10万以下免征）":
        rt = p.get("reg_type")
        if not rt:
            return "unknown", "需确认注册类型"
        if rt == "个体工商户":
            return "match", f"注册类型为个体工商户"
        return "no", f"注册类型（{rt}）非个体工商户"

    if "小型微利企业" in cond:
        rev = p.get("revenue")
        ts = p.get("team_size")
        if not rev and not ts:
            return "unknown", "需确认营收与团队规模"
        # 小型微利 = 应纳税所得额≤300万 + 人数≤300 + 资产≤5000万（前面已判）
        return "match", "营收/人数在小型微利标准内"

    # --- 小规模纳税人 ---
    if "小规模纳税人" in cond:
        return "match", "个体工商户/低营收企业默认为小规模纳税人（年销售额超500万自动转一般纳税人）"

    # --- 软件 / 研发 ---
    if "研发活动" in cond:
        ind = p.get("industry") or ""
        if not ind:
            return "unknown", "需确认行业"
        if any(k in ind for k in ("软件", "AI", "人工智能", "研发", "开发", "科技")):
            return "match", f"行业（{ind}）存在研发投入（含大模型 API 费用）"
        return "no", f"行业（{ind}）暂无明确研发活动"

    if "研发费用" in cond and ("立账" in cond or "辅助账" in cond or "加计" in cond):
        has = p.get("has_materials") or ""
        if not has:
            return "unknown", "需确认是否建立研发费用辅助账"
        if "研发" in has or "辅助账" in has:
            return "match", "已建立研发费用辅助账"
        return "unknown", "需确认研发费用是否单独立账"

    if "研发费用占比" in cond:
        return "unknown", "需研发费用专项审计确认占比"

    if "自行开发软件产品" in cond or "自行开发" in cond:
        ind = p.get("industry") or ""
        if not ind:
            return "unknown", "需确认行业"
        if any(k in ind for k in ("软件", "开发", "AI", "编程")):
            return "match", f"行业（{ind}）为自行开发"
        return "no", f"行业（{ind}）非软件开发"

    if "软件产品已登记" in cond or "软件产品登记" in cond:
        has = p.get("has_materials") or ""
        if "软件产品登记" in has:
            return "match", "已取得软件产品登记证书"
        return "unknown", "需确认是否取得软件产品登记证书（软著登记 1-3 个月）"

    if "软件收入占比" in cond:
        ind = p.get("industry") or ""
        if not ind:
            return "unknown", "需确认行业"
        if any(k in ind for k in ("软件", "开发", "AI")):
            return "match", f"行业（{ind}）以软件收入为主"
        return "no", "非软件收入为主"

    # --- 创业大赛获奖 ---
    if "大赛" in cond and "获奖" in cond:
        return "unknown", "需确认是否已获得市级以上创业大赛奖项"

    # --- 无住房 ---
    if "无住房" in cond or "无房" in cond:
        return "unknown", "需确认在温州是否有自有住房"

    # --- 入驻 OPC 中心 ---
    if "入驻" in cond:
        return "unknown", "需确认是否已入驻 OPC 创业中心"

    # --- 算力采购 ---
    if "算力" in cond or "采购智能算力" in cond:
        ind = p.get("industry") or ""
        if ind and any(k in ind for k in ("软件", "AI", "开发", "科技")):
            return "match", f"行业（{ind}）有算力/模型采购需求"
        return "unknown", "需确认是否采购算力/模型服务"

    if "合同真实" in cond or "已支付" in cond:
        return "unknown", "需确认采购合同与付款凭证"

    # --- 默认（未识别的条件）---
    return "unknown", f"「{cond}」需人工确认"


# ---------- 政策匹配 ----------
def match_policies(profile: dict, region: str = "wenzhou", include_national: bool = True) -> list[dict]:
    """按地区匹配政策（national + 该地区）。

    include_national=False 时只匹配该地区差异化政策（国家级人人都有，
    不算「差异化机会」，用于政策机会指数/健康指数的政策维度）。

    Returns: [
        {policy, status, matched_conditions, unmet_conditions, pending_conditions}
    ]
    """
    pool = all_policies(region)
    if not include_national:
        pool = [p for p in pool if p.get("region") != "national"]

    results = []
    for pol in pool:
        # 隔离层：未核实地区的地区政策（非国家级）永远不进入 match，
        # 仅作"待核实参考"展示 → 政策机会指数/材料清单都不会被未核实数据污染。
        if pol.get("region") != "national" and not _is_verified(region):
            results.append({
                "policy": pol,
                "status": "unknown",
                "matched_conditions": [],
                "unmet_conditions": [],
                "pending_conditions": [{
                    "condition": "该地区政策数据为自助导入/占位，未人工核实",
                    "reason": "导入数据·待核实，不纳入正式申请匹配（保证零造假）",
                }],
            })
            continue

        matched, unmet, pending = [], [], []
        for cond in pol["eligibility"]:
            status, reason = _check_condition(cond, profile)
            if status == "match":
                matched.append({"condition": cond, "reason": reason})
            elif status == "no":
                unmet.append({"condition": cond, "reason": reason})
            else:
                pending.append({"condition": cond, "reason": reason})

        if unmet:
            status = "no"
        elif pending:
            status = "unknown"
        else:
            status = "match"

        results.append({
            "policy": pol,
            "status": status,
            "matched_conditions": matched,
            "unmet_conditions": unmet,
            "pending_conditions": pending,
        })
    return results


def matched_policies(profile: dict, region: str, include_national: bool = True) -> list[dict]:
    """返回可直接申请（match）的政策。include_national=False 只算地区差异化政策。"""
    return [r for r in match_policies(profile, region, include_national) if r["status"] == "match"]


def policy_opportunity_count(profile: dict, region: str) -> int:
    """政策机会指数 = 地区差异化可申请政策数（国家级人人都有，不计入「机会」）。"""
    return len(matched_policies(profile, region, include_national=False))


def policy_match_rate(profile: dict, region: str) -> int:
    """政策匹配度 = match / (match + no)，排除待确认（unknown）。"""
    rs = match_policies(profile, region)
    evaluated = [r for r in rs if r["status"] in ("match", "no")]
    if not evaluated:
        return 0
    matched = sum(1 for r in evaluated if r["status"] == "match")
    return round(matched / len(evaluated) * 100)


# ---------- 材料清单 ----------
_MATERIAL_KEYWORDS = {
    "身份证": "身份证",
    "毕业证": "毕业证",
    "学位证": "学位证",
    "营业执照": "营业执照",
    "章程": "章程",
    "开户": "开户",
    "公章": "公章",
    "场所": "场所",
    "社保": "社保",
    "劳动合同": "合同",
    "发票": "发票",
    "付款": "付款",
    "审计": "审计",
    "软著": "软著",
    "软件产品登记": "软件产品登记",
    "商业计划书": "商业计划书",
}


def _material_status(name: str, profile: dict) -> str:
    """判断材料已备/缺失/待确认/自动。

    - '自动'：告知性条目（'系统自动享受''无需单独申请'），非真实要准备的材料
    - '待确认'：用户尚未提供任何材料信息
    """
    has = profile.get("has_materials") or ""
    if any(k in name for k in ("自动", "无需", "系统")):
        return "自动"
    if not has:
        return "待确认"
    for mat_kw, detect_kw in _MATERIAL_KEYWORDS.items():
        if mat_kw in name:
            if detect_kw in has:
                return "已备"
            return "缺失"
    # 未映射到的材料：若用户给了材料列表但没提这个 → 缺失
    return "缺失"


def _norm_material(name: str) -> str:
    """材料名归一化：去掉括号注释，用于跨政策去重（'经营场所证明（OPC中心入驻协议即可）' 与 '经营场所证明' 视为同一材料）。"""
    return re.sub(r"[（(].*?[)）]", "", name).strip()


def build_checklist(profile: dict, region: str) -> list[dict]:
    """生成材料清单：对 match + unknown（待确认）政策收集材料，标注已备/缺失/待确认。"""
    results = match_policies(profile, region)
    items: list[dict] = []
    seen = set()
    for mr in results:
        if mr["status"] == "no":
            continue  # 不列被资格否决政策的要求
        if mr["policy"].get("region") == "general":
            continue  # 通用参考政策不列材料（不代表当地一定有）
        if mr["policy"].get("region") != "national" and not _is_verified(region):
            continue  # 隔离层：未核实地区政策不列材料（零造假，防止错误数据污染清单）
        for mat in mr["policy"]["materials"]:
            key = mat["name"]
            norm = _norm_material(key)
            if norm in seen:
                continue
            seen.add(norm)
            items.append({
                "name": key,
                "status": _material_status(key, profile),
                "format_note": mat.get("format_note", ""),
                "policy_id": mr["policy"]["id"],
                "policy_name": mr["policy"]["name"],
                "source": mr["policy"].get("source", ""),  # 来源机构（驾驶舱"去哪办"提示，F19）
            })
    # 排序：缺失 > 待确认 > 已备 > 自动（自动项不参与待办统计）
    order = {"缺失": 0, "待确认": 1, "已备": 2, "自动": 3}
    items.sort(key=lambda x: order.get(x["status"], 3))
    return items


# ---------- 风险 ----------
def assess_risk(profile: dict) -> dict:
    """风险评估：客户集中 / 社保缺口 / 现金流缓冲。"""
    risks = []
    p = profile

    cc = p.get("client_concentration")
    if cc:
        n = _to_num(cc)
        if n is not None and n >= 50:
            risks.append({"type": "客户集中风险", "level": "高",
                          "desc": f"单一客户占比约{n:.0f}%",
                          "advice": "核心客户流失=收入断裂，建议分散客户来源"})
        elif n is not None and n >= 30:
            risks.append({"type": "客户集中风险", "level": "中",
                          "desc": f"单一客户占比约{n:.0f}%",
                          "advice": "关注客户集中度，逐步分散"})

    ss = p.get("social_security")
    if ss in ("无", "没有", "否", "未缴"):
        risks.append({"type": "社保缺口", "level": "中",
                      "desc": "未缴纳社保",
                      "advice": "开通社保：既是政策资格（多项补贴要求社保），也是个人保障覆盖"})

    cb = p.get("cash_buffer")
    if cb:
        n = _to_num(cb)
        if n is not None and n < 3:
            risks.append({"type": "现金流缓冲不足", "level": "高",
                          "desc": f"现金约可撑{n:.0f}个月",
                          "advice": "低于3个月缓冲，建议储备应急资金并建立月收入基准线"})
        elif n is not None and n < 6:
            risks.append({"type": "现金流缓冲偏紧", "level": "中",
                          "desc": f"现金约可撑{n:.0f}个月",
                          "advice": "中期偏紧，建议规划月现金流"})

    if not risks:
        risks.append({"type": "综合风险", "level": "低",
                      "desc": "未发现显著风险项",
                      "advice": "保持当前经营节奏，定期体检"})

    # 综合等级特判（对齐 PPT「风险中·重点关注」语义）：
    # - 现金流缓冲不足(<3月) 或 单一客户>80% → 综合「高」
    # - 客户集中高(50-80%) 但现金流安全(≥3月) → 综合「中」（重点关注，不是致命）
    cc_num = _to_num(p.get("client_concentration"))
    cash_critical = any(r["type"] == "现金流缓冲不足" for r in risks)
    client_extreme = cc_num is not None and cc_num > 80
    if cash_critical or client_extreme:
        level = "高"
    elif any(r["level"] == "高" for r in risks):
        level = "中"  # 有高优先级风险项但现金流安全 → 中
    elif any(r["level"] == "中" for r in risks):
        level = "中"
    else:
        level = "低"

    return {"level": level, "risks": risks}


# ---------- 综合摘要 ----------
def summary(profile: dict, region: str = "wenzhou") -> dict:
    """综合输出（供驾驶舱）。"""
    info = region_info(region)
    matched = matched_policies(profile, region)
    return {
        "region": info.get("name", region),
        "region_status": info.get("data_status", ""),
        "matched_policies": [m["policy"] for m in matched],
        "opportunity_count": len(matched),
        "match_rate": policy_match_rate(profile, region),
        "checklist": build_checklist(profile, region),
        "risk": assess_risk(profile),
    }
