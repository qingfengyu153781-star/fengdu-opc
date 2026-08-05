# -*- coding: utf-8 -*-
"""地区注册表：地区代码 → 政策库模块。

设计原则：**不预置一堆城市**。只有演示用的温州/杭州有真实数据，
用户输入任意其他地区 → 实时联网搜索当地政策（见 utils/policy_searcher.py），
并叠加通用政策方向库兜底（见 policies/general.py）。

任何地区政策库 = 国家级通用(national) + 该地区自己的政策。
"""

from . import national, wenzhou, hangzhou, general

# 地区注册表：地区 code → 模块
# 只有演示用真实库（温州/杭州）。用户输入的其他地区 → 实时搜索 + 通用方向。
REGIONS = {
    "wenzhou": wenzhou,
    "hangzhou": hangzhou,
}

# 地区下拉展示用（code → 展示名）
REGION_LABELS = {
    "national": "国家级（全国通用）",
    "wenzhou": "温州",
    "hangzhou": "杭州",
}

# 未收录地区 → 用通用政策方向库兜底（实时搜索之外的最低保障）
FALLBACK_REGION = general


def get_region(region_code: str):
    """返回地区模块，未知地区返回 None（由上层实时搜索 + 通用兜底处理）。"""
    return REGIONS.get(region_code)


def all_policies(region_code: str) -> list[dict]:
    """地区全部政策 = national + 该地区政策（national 永远第一优先级）。

    未收录地区 → national + general（通用政策方向，标注「通用参考·需核验」）。
    """
    region_mod = REGIONS.get(region_code)
    if region_mod is None:
        return list(national.POLICIES) + list(FALLBACK_REGION.POLICIES)
    return list(national.POLICIES) + list(region_mod.POLICIES)


def region_info(region_code: str) -> dict:
    """地区元信息（用于 UI 显示数据状态/更新时间）。"""
    region_mod = get_region(region_code)
    info = {
        "code": region_code,
        "name": REGION_LABELS.get(region_code, region_code),
        "data_status": "通用参考·需核验",
        "update_date": "-",
        "note": "未收录地区：实时搜索当地政策 + 通用方向兜底",
    }
    if region_mod is not None:
        info.update(region_mod.REGION)
    return info


def available_regions() -> list[str]:
    """返回已注册地区 code（供下拉选择；用户可自由输入任意地区）。"""
    return list(REGIONS.keys())
