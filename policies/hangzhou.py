# -*- coding: utf-8 -*-
"""政策导入生成（2026-08）—— 来源：用户粘贴原文 + LLM 结构化，请人工核对。"""

REGION = {
    "name": "杭州",
    "code": "hangzhou",
    "data_status": "导入数据·待核对",
    "update_date": "2026-08",
    "note": "由政策导入功能生成，请核对与官方文件一致",
}

POLICIES = [
    {
        "id": 'HZ-EX',
        "name": '（示例占位）杭州创业扶持政策待导入',
        "region": 'hangzhou',
        "category": '创业启动',
        "amount": '待补充',
        "source": '待补充（以官方发布为准）',
        "source_url": 'https://www.hangzhou.gov.cn/',
        "difficulty": '待评估',
        "timing": '待补充',
        "key_point": '示例占位，不构成政策建议。切换到本地区可展示国家级通用政策仍生效。',
        "update_date": '2026-08',
        "eligibility": ['真实政策条件待补充'],
        "materials": [{'name': '待补充', 'required': True}],
    },
    {
        "id": 'IMP-2',
        "name": '11111',
        "region": 'hangzhou',
        "category": '其他',
        "amount": '以官方文件为准',
        "source": '以官方文件为准',
        "source_url": '',
        "difficulty": '待评估',
        "timing": '以当地官方为准',
        "key_point": '规则解析自动入库，请人工核对与官方原文一致',
        "update_date": '2026-08',
        "eligibility": ['以当地官方文件为准'],
        "materials": [{'name': '以当地官方要求为准', 'required': True}],
    },
]