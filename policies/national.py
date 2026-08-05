# -*- coding: utf-8 -*-
"""国家级通用政策库 —— 任何地区都自动叠加匹配。

政策数据来源：
- 《财政部 税务总局关于小微企业和个体工商户所得税优惠政策的公告》
- 《财政部 税务总局关于明确增值税小规模纳税人减免增值税等政策的公告》
- 国家税务总局官方发布平台（www.chinatax.gov.cn）

诚实标注：本库只收录长期稳定的国家级通用政策，地区性政策见 policies/<region>.py。
金额/比例均为政策原文口径，如有更新以官方最新公告为准（见 policy_updater 更新机制）。
"""

REGION = {
    "name": "国家级（全国通用）",
    "code": "national",
    "data_status": "真实数据",
    "update_date": "2026-07",
    "note": "任何地区选择时自动叠加此库",
}

POLICIES = [
    {
        "id": "N1",
        "name": "小型微利企业所得税优惠（实际税负约5%）",
        "region": "national",
        "category": "税务减免",
        "amount": "年应纳税所得额≤300万，实际税负约5%",
        "eligibility": [
            "年度应纳税所得额不超过300万元",
            "从业人数不超过300人",
            "资产总额不超过5000万元",
            "从事国家非限制和禁止行业",
        ],
        "materials": [
            {"name": "季度预缴申报表（系统自动享受，无需备案）", "required": True, "format_note": "由申报系统自动计算"},
        ],
        "source": "财政部 税务总局公告",
        "source_url": "https://www.chinatax.gov.cn/",
        "difficulty": "低",
        "timing": "季度申报时自动适用，从注册第一天就保护你",
        "key_point": "报税自动适用——这是「名字像大企业的事，实际是给单人公司用的」典型案例",
        "update_date": "2026-07",
    },
    {
        "id": "N2",
        "name": "增值税小规模纳税人减免（月销售额10万以下免征）",
        "region": "national",
        "category": "税务减免",
        "amount": "月销售额10万以下（季度30万）免征增值税",
        "eligibility": [
            "增值税小规模纳税人",
            "月销售额不超过10万元（按季申报季度不超过30万元）",
        ],
        "materials": [
            {"name": "增值税申报表（系统自动判断免征）", "required": True, "format_note": "申报时系统自动识别"},
        ],
        "source": "财政部 税务总局公告",
        "source_url": "https://www.chinatax.gov.cn/",
        "difficulty": "低",
        "timing": "按季/按月申报时自动适用",
        "key_point": "一人公司月营收 10 万以内基本不用交增值税",
        "update_date": "2026-07",
    },
    {
        "id": "N3",
        "name": "六税两费减半征收",
        "region": "national",
        "category": "税务减免",
        "amount": "资源税、城建税、房产税、城镇土地使用税、印花税、耕地占用税、教育费附加、地方教育附加减半",
        "eligibility": [
            "增值税小规模纳税人",
            "小型微利企业",
            "个体工商户",
        ],
        "materials": [
            {"name": "申报表（系统自动减半，无需额外材料）", "required": True, "format_note": "自动享受"},
        ],
        "source": "财政部 税务总局公告",
        "source_url": "https://www.chinatax.gov.cn/",
        "difficulty": "低",
        "timing": "申报时自动适用",
        "key_point": "小税种减半，积少成多，无需申请",
        "update_date": "2026-07",
    },
    {
        "id": "N4",
        "name": "研发费用税前加计扣除",
        "region": "national",
        "category": "资质/税务",
        "amount": "研发费用在税前扣除基础上再加计扣除",
        "eligibility": [
            "有实际研发活动的企业",
            "研发费用单独立账（辅助账）",
            "研发人员/设备/材料等支出可计入",
        ],
        "materials": [
            {"name": "研发费用辅助账", "required": True, "format_note": "从 Day 1 就要记清楚哪些是研发支出"},
            {"name": "研发项目立项文件", "required": True, "format_note": "内部立项说明即可"},
        ],
        "source": "财政部 税务总局公告 · 国家税务总局",
        "source_url": "https://www.chinatax.gov.cn/",
        "difficulty": "中",
        "timing": "年度汇算清缴时申报",
        "key_point": "对单人软件公司：DeepSeek/大模型 API 费用可计入研发投入——这是单人也能用的隐形福利",
        "update_date": "2026-07",
    },
]
