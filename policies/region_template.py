# -*- coding: utf-8 -*-
"""新地区政策库模板 —— 复制本文件为 policies/<new_code>.py 填真实数据。

用法：
1. 复制：cp region_template.py <new_code>.py
2. 改 REGION 元信息（code 必须是英文小写，如 "beijing"）
3. 用真实政策数据替换 POLICIES 列表（不要编造！）
4. 在 policies/__init__.py 的 REGIONS 里注册

或者更快：直接在 Demo 的「政策导入」页粘贴政策原文，让 AI 帮你结构化入库。
"""

# 地区元信息 —— 必填
REGION = {
    "name": "新地区",            # 展示名，如 "北京"
    "code": "new_region",       # 英文小写代码，如 "beijing"
    "data_status": "待补充",     # 真实数据 / 示例数据·待补充 / 待补充
    "update_date": "2026-08",   # 最近更新
    "note": "待补充真实政策数据",  # 说明
}

# 政策列表 —— 每项结构见 wenzhou.py 注释
POLICIES = [
    {
        "id": "X1",
        "name": "示例政策名称",
        "region": "new_region",
        "category": "创业启动",   # 创业启动 / 社保生活 / 资质税务 / 其他
        "amount": "¥0",
        "eligibility": ["条件1", "条件2"],
        "materials": [
            {"name": "材料1", "required": True, "format_note": "格式说明（可选）"},
        ],
        "source": "政策来源机构",
        "source_url": "https://官方平台域名/",
        "difficulty": "低",       # 低 / 中 / 高
        "timing": "申请时机",
        "key_point": "一句话要点",
        "update_date": "2026-08",
    },
    # ... 继续填更多政策
]
