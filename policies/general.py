# -*- coding: utf-8 -*-
"""通用政策方向库（面向未收录地区）。

用途：用户所在地区不在已核实库（温州/杭州）时，返回全国常见的创业/经营政策方向，
让「枫独」对任意地区都有参考可给，不局限于内置城市。

⚠️ 零造假保障：
- 本库是「常见政策方向」而非「当地真实政策」——金额/资格/材料都用「以当地官方为准」措辞。
- 条件写成待核验（不写死本地判定）→ 这些政策不会计入「政策机会」数字，只作为参考展示。
- 展示标签「通用参考·需核验」，引导用户用 ④政策导入 录入当地真实政策。
"""

REGION = {
    "name": "通用参考",
    "code": "general",
    "data_status": "通用参考·需核验",
    "update_date": "2026-07",
    "note": "未收录地区的常见政策方向，具体以当地官方最新文件为准",
}

POLICIES = [
    {
        "id": "G1",
        "name": "一次性创业补贴（当地）",
        "region": "general",
        "category": "创业启动",
        "amount": "以当地为准（各地通常 1-10 万元不等）",
        "eligibility": [
            "在本地注册个体工商户/小微企业",
            "正常经营",
            "各地要求不一（部分限毕业 X 年内/首次创业/带动就业）",
        ],
        "materials": [
            {"name": "身份证", "required": True},
            {"name": "营业执照", "required": True},
            {"name": "银行账户", "required": True},
        ],
        "source": "当地人社 / 政务服务平台",
        "source_url": "",
        "difficulty": "低",
        "timing": "注册后咨询当地人社窗口",
        "key_point": "各地金额/门槛差异大，务必以当地人社部门最新文件为准",
        "update_date": "2026-07",
    },
    {
        "id": "G2",
        "name": "创业担保贷款 / 贴息（当地）",
        "region": "general",
        "category": "创业启动",
        "amount": "以当地为准（常见额度 10-30 万，部分贴息）",
        "eligibility": [
            "在本地创业",
            "各地对信用/抵押/带动就业要求不一",
        ],
        "materials": [
            {"name": "营业执照", "required": True},
            {"name": "经营流水或资产证明", "required": True},
        ],
        "source": "当地人社局 + 合作银行",
        "source_url": "",
        "difficulty": "中",
        "timing": "注册后即可咨询",
        "key_point": "额度/利率/贴息各地不同，需以当地政策为准",
        "update_date": "2026-07",
    },
    {
        "id": "G3",
        "name": "人才/生活补贴（当地）",
        "region": "general",
        "category": "社保/生活",
        "amount": "以当地为准（常见本科到博士数千到数万元/年）",
        "eligibility": [
            "学历达到当地人才标准",
            "在本地就业/创业并缴纳社保",
            "各地对毕业年限/社保要求不一",
        ],
        "materials": [
            {"name": "学历学位证", "required": True},
            {"name": "社保缴纳证明", "required": True},
            {"name": "身份证", "required": True},
        ],
        "source": "当地人才办 / 人才服务平台",
        "source_url": "",
        "difficulty": "低",
        "timing": "落户/就业/创业后",
        "key_point": "各地人才政策差异大，需以当地人才办最新文件为准",
        "update_date": "2026-07",
    },
    {
        "id": "G4",
        "name": "租房补贴 / 人才公寓（当地）",
        "region": "general",
        "category": "社保/生活",
        "amount": "以当地为准（各地有月度租房补贴或人才公寓）",
        "eligibility": [
            "当地无住房",
            "学历/社保达到当地要求",
        ],
        "materials": [
            {"name": "无房证明", "required": True},
            {"name": "学历证明", "required": True},
        ],
        "source": "当地住建 / 人才平台",
        "source_url": "",
        "difficulty": "低",
        "timing": "到当地后",
        "key_point": "补贴与公寓通常二选一，具体以当地为准",
        "update_date": "2026-07",
    },
    {
        "id": "G5",
        "name": "社保 / 就业补贴（当地）",
        "region": "general",
        "category": "社保/生活",
        "amount": "以当地为准",
        "eligibility": [
            "在本地创业并缴纳社保",
            "或招用员工（含兼职）带动就业",
        ],
        "materials": [
            {"name": "社保缴纳记录", "required": True},
            {"name": "营业执照", "required": True},
        ],
        "source": "当地人社",
        "source_url": "",
        "difficulty": "低",
        "timing": "缴纳社保/招人后",
        "key_point": "一人公司招兼职也算带动就业，各地鼓励政策不同",
        "update_date": "2026-07",
    },
    {
        "id": "G6",
        "name": "租金减免 / 场地支持（当地）",
        "region": "general",
        "category": "创业启动",
        "amount": "以当地为准（常见：孵化器/创业园房租减免）",
        "eligibility": [
            "入驻当地创业孵化器/产业园",
            "提交入驻申请",
        ],
        "materials": [
            {"name": "入驻申请", "required": True},
            {"name": "商业计划书（部分需要）", "required": True},
        ],
        "source": "当地创业服务中心 / 孵化器",
        "source_url": "",
        "difficulty": "低",
        "timing": "入驻时",
        "key_point": "各地孵化器政策不同，入驻前先问清减免条件",
        "update_date": "2026-07",
    },
    {
        "id": "G7",
        "name": "创业大赛 / 项目资助（当地）",
        "region": "general",
        "category": "创业启动",
        "amount": "以当地为准（各地有大赛奖金/立项资助）",
        "eligibility": [
            "项目在本地落地",
            "获奖或立项（各地要求不一）",
        ],
        "materials": [
            {"name": "商业计划书", "required": True},
            {"name": "项目材料", "required": True},
        ],
        "source": "当地科技/人社部门",
        "source_url": "",
        "difficulty": "中",
        "timing": "关注当地大赛/立项通知",
        "key_point": "大赛与立项资助是创业初期的常见资金来源",
        "update_date": "2026-07",
    },
    {
        "id": "G8",
        "name": "税收优惠 / 减免（当地适用）",
        "region": "general",
        "category": "资质/税务",
        "amount": "以当地及国家现行政策为准",
        "eligibility": [
            "个体工商户/小微企业可享的国家级减免（见国家级政策）",
            "部分当地还有额外减免（各地不同）",
        ],
        "materials": [
            {"name": "按当地申报要求", "required": True},
        ],
        "source": "当地税务局",
        "source_url": "",
        "difficulty": "低",
        "timing": "申报时",
        "key_point": "国家级减免全国通用（本报告已列），当地额外减免需咨询当地税务",
        "update_date": "2026-07",
    },
]
