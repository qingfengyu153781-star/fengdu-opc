# -*- coding: utf-8 -*-
"""OPC 经营状态模型：6 维状态向量 + 三指数计算（核心创新）。

对应 PPT P11/P12 的公式设计：
    6 维状态向量 X = [个人依赖度, 收入来源集中度, 订单生命周期, 客户集中风险, 现金流缓冲能力, 经营连续性]
    健康指数 H = 5 个可量化维度等权 20% 打分（0-100），透明可解释
    政策机会指数 P = 规则引擎命中的可申请政策数
    风险指数 R = 规则引擎风险等级

打分规则是公开的产品定义（不是黑盒），每个维度都带解释。
"""
from __future__ import annotations

import re

from utils.rule_engine import matched_policies, assess_risk, policy_match_rate


def _num(text) -> float | None:
    m = re.search(r"([\d.]+)", str(text))
    return float(m.group(1)) if m else None


# ---------- 6 维状态向量 ----------
def build_state_vector(profile: dict) -> list[dict]:
    """从经营信息推导 6 维状态向量。"""
    p = profile
    vec = []

    # 1. 个人依赖度
    ts = p.get("team_size")
    tsn = _num(ts)
    if tsn is not None and tsn <= 1:
        vec.append({"name": "个人依赖度", "value": "高", "note": "单人工作室，无备份"})
    elif tsn is not None and tsn <= 3:
        vec.append({"name": "个人依赖度", "value": "中", "note": "小团队，仍依赖创始人"})
    else:
        vec.append({"name": "个人依赖度", "value": "低", "note": "团队可分担"})

    # 2. 收入来源集中度
    cc = p.get("client_concentration")
    ccn = _num(cc)
    if ccn is not None and ccn >= 50:
        vec.append({"name": "收入来源集中度", "value": "高", "note": f"单客户{cc}"})
    elif ccn is not None and ccn >= 30:
        vec.append({"name": "收入来源集中度", "value": "中", "note": f"单客户{cc}"})
    elif ccn is not None:
        vec.append({"name": "收入来源集中度", "value": "低", "note": f"单客户{cc}"})
    else:
        vec.append({"name": "收入来源集中度", "value": "待评估", "note": "缺客户分布数据"})

    # 3. 订单生命周期
    oc = p.get("order_cycle")
    if oc:
        vec.append({"name": "订单生命周期", "value": "中", "note": oc})
    else:
        vec.append({"name": "订单生命周期", "value": "待评估", "note": "缺订单周期数据"})

    # 4. 客户集中风险
    if ccn is not None and ccn >= 50:
        vec.append({"name": "客户集中风险", "value": "高风险", "note": "核心客户流失=收入断裂"})
    elif ccn is not None and ccn >= 30:
        vec.append({"name": "客户集中风险", "value": "中", "note": "单一客户占比偏高"})
    else:
        vec.append({"name": "客户集中风险", "value": "低", "note": "客户分布分散"})

    # 5. 现金流缓冲能力
    cb = p.get("cash_buffer")
    cbn = _num(cb)
    if cbn is not None and cbn >= 6:
        vec.append({"name": "现金流缓冲能力", "value": "强", "note": f"约{cbn}个月缓冲"})
    elif cbn is not None and cbn >= 3:
        vec.append({"name": "现金流缓冲能力", "value": "中", "note": f"约{cbn}个月缓冲（短期安全）"})
    elif cbn is not None:
        vec.append({"name": "现金流缓冲能力", "value": "弱", "note": f"约{cbn}个月缓冲（偏紧）"})
    else:
        vec.append({"name": "现金流缓冲能力", "value": "待评估", "note": "缺现金流数据"})

    # 6. 经营连续性
    dur = p.get("duration")
    dn = _num(dur)
    if dn is not None:
        years = dn if "年" in str(dur) else dn / 12
        if years >= 2:
            vec.append({"name": "经营连续性", "value": "中", "note": f"已经营约{years:.0f}年"})
        elif years >= 1:
            vec.append({"name": "经营连续性", "value": "中", "note": f"已经营约{years:.1f}年"})
        else:
            vec.append({"name": "经营连续性", "value": "低", "note": f"经营不足1年"})
    else:
        vec.append({"name": "经营连续性", "value": "待评估", "note": "缺经营时长数据"})

    return vec


# ---------- 健康指数（5 维等权 20%） ----------
def _score_revenue_stability(profile: dict) -> tuple[int, str]:
    cc = profile.get("client_concentration")
    n = _num(cc)
    if n is None:
        return 65, "客户集中度未知（按中性计）"
    if n >= 70:
        return 30, f"单一客户{n:.0f}%，高度依赖"
    if n >= 50:
        return 45, f"单一客户{n:.0f}%，集中度偏高"
    if n >= 30:
        return 60, f"单一客户{n:.0f}%，需关注"
    return 80, f"单一客户{n:.0f}%，分散良好"


def _score_cash_safety(profile: dict) -> tuple[int, str]:
    cb = profile.get("cash_buffer")
    n = _num(cb)
    if n is None:
        return 55, "现金流缓冲未知（按中性计）"
    if n >= 6:
        return 95, f"{n:.0f}个月缓冲，安全"
    if n >= 3:
        return 90, f"{n:.0f}个月缓冲，短期安全"
    if n >= 1:
        return 60, f"{n:.0f}个月缓冲，偏紧"
    return 30, f"{n:.0f}个月缓冲，危险"


def _score_cost_control(profile: dict) -> tuple[int, str]:
    cost = profile.get("cost")
    rev = profile.get("revenue")
    cn = _num(cost)
    rn = _num(rev)
    if cn is None or rn is None or rn <= 0:
        return 70, "成本/营收比未知（按中性偏乐观计）"
    ratio = cn / rn
    if ratio <= 0.4:
        return 90, f"成本占比{ratio:.0%}，控制良好"
    if ratio <= 0.7:
        return 70, f"成本占比{ratio:.0%}，合理"
    if ratio <= 0.9:
        return 50, f"成本占比{ratio:.0%}，偏高"
    return 30, f"成本占比{ratio:.0%}，接近盈亏平衡"


def _score_policy_match(profile: dict, region: str) -> tuple[int, str]:
    # 政策机会只算地区差异化政策（国家级人人都有，不算「机会」）
    matched = len(matched_policies(profile, region, include_national=False))
    if matched >= 5:
        return 88, f"匹配{matched}项地区可申请政策，政策环境友好"
    if matched == 4:
        return 82, f"匹配{matched}项地区可申请政策"
    if matched == 3:
        return 75, f"匹配{matched}项地区可申请政策"
    if matched == 2:
        return 65, f"匹配{matched}项地区可申请政策"
    if matched == 1:
        return 55, f"匹配{matched}项地区可申请政策"
    return 40, "暂无直接可申请政策（可能有待确认项）"


def _score_business_cycle(profile: dict) -> tuple[int, str]:
    dur = profile.get("duration")
    dn = _num(dur)
    if dn is None:
        return 50, "经营时长未知（按中性计）"
    years = dn if "年" in str(dur) else dn / 12
    if years >= 3:
        return 90, f"经营{years:.0f}年，已过初创期"
    if years >= 2:
        return 80, f"经营{years:.0f}年，初具连续性"
    if years >= 1:
        return 65, f"经营{years:.1f}年，渡过了第一年"
    return 40, f"经营不足1年，处于初创期"


def compute_indices(profile: dict, region: str = "wenzhou") -> dict:
    """三指数计算。"""
    s1, r1 = _score_revenue_stability(profile)
    s2, r2 = _score_cash_safety(profile)
    s3, r3 = _score_cost_control(profile)
    s4, r4 = _score_policy_match(profile, region)
    s5, r5 = _score_business_cycle(profile)

    health = round((s1 + s2 + s3 + s4 + s5) / 5)

    # 政策机会指数 = 地区差异化政策（国家级自动享受另计，报告里列全量）
    matched_all = matched_policies(profile, region)
    matched_local = matched_policies(profile, region, include_national=False)
    risk = assess_risk(profile)

    return {
        "health": health,
        "health_dims": [
            {"name": "收入稳定", "score": s1, "reason": r1, "weight": "20%"},
            {"name": "现金流安全", "score": s2, "reason": r2, "weight": "20%"},
            {"name": "成本控制", "score": s3, "reason": r3, "weight": "20%"},
            {"name": "政策匹配", "score": s4, "reason": r4, "weight": "20%"},
            {"name": "经营周期", "score": s5, "reason": r5, "weight": "20%"},
        ],
        "policy_opportunity": len(matched_local),
        "policy_names": [m["policy"]["name"] for m in matched_all],
        "policy_names_local": [m["policy"]["name"] for m in matched_local],
        "policy_names_national": [m["policy"]["name"] for m in matched_all
                                  if m["policy"].get("region") == "national"],
        "risk": risk,
        "state_vector": build_state_vector(profile),
    }


def build_recommendations(profile: dict, indices: dict) -> list[str]:
    """基于风险与状态向量生成行动建议。"""
    recs = []
    for r in indices["risk"]["risks"]:
        if r["level"] in ("高", "中"):
            recs.append(r["advice"])
    # 政策机会建议
    if indices["policy_opportunity"] > 0:
        recs.append(f"尽快准备材料申请「{'、'.join(indices['policy_names'][:2])}」等 {indices['policy_opportunity']} 项政策")
    # 去重保序
    seen, out = set(), []
    for x in recs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out[:5]
