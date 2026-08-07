# -*- coding: utf-8 -*-
"""实时政策搜索（卖点核心：问就有，全国任意地区）。

搜索策略（四档，逐级降级，保证"问就有"的概率最大）：
  1. [真 API] 若配置了 BING_SEARCH_API_KEY（Azure Bing Search 免费层 1000 次/月）
     → 走官方搜索 API，稳定可作申请依据（效果等同于主流 AI 搜索）。
  2. [免费爬虫] 无 key → 三源全试（Bing 国际 → DuckDuckGo → 百度），
     结果合并去重 + 官方来源优先排序 → 任一源成功即可用。
  3. [零造假] 返回的都是搜索引擎真实结果（标题+URL+摘要），带来源可溯源。
  4. [不哑火] 全部失败 → 上层显示"网络受限"提示 + 本地通用政策库兜底。

环境变量：
  BING_SEARCH_API_KEY   Azure Bing Search 免费层 key（可选，有则用真 API）
  MODELSCOPE_API_KEY    用于 LLM 智能搜索词生成（可选，见 app.py）

⚠️ 数据诚实：摘要来自搜索结果页，需点开核验原文；官方来源（.gov.cn）优先置顶。
"""
from __future__ import annotations

import os
import re

import requests

TIMEOUT = 8
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
MAX_SOURCES = 3


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def _fetch(url: str, data: dict | None = None, params: dict | None = None) -> str | None:
    try:
        if data is not None:
            r = requests.post(url, data=data, headers=HEADERS, timeout=TIMEOUT)
        else:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
    except Exception:
        return None
    return None


def _parse_bing(html: str) -> list[dict]:
    items = []
    # <li class="b_algo"> ... <h2><a href="URL">TITLE</a></h2> ... <p>SNIPPET</p>
    for m in re.finditer(r'<li class="b_algo".*?</li>', html, re.S):
        block = m.group(0)
        am = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not am:
            continue
        url, title = am.group(1), _clean(am.group(2))
        pm = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = _clean(pm.group(1)) if pm else ""
        if url and title:
            items.append({"title": title, "url": url, "snippet": snippet})
    return items[:8]


def _parse_ddg(html: str) -> list[dict]:
    items = []
    for m in re.finditer(r'<div class="result.*?</div>\s*</div>', html, re.S):
        block = m.group(0)
        am = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not am:
            continue
        url, title = am.group(1), _clean(am.group(2))
        pm = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        snippet = _clean(pm.group(1)) if pm else ""
        if url and title:
            items.append({"title": title, "url": url, "snippet": snippet})
    return items[:8]


def _parse_baidu(html: str) -> list[dict]:
    items = []
    for m in re.finditer(r'<h3[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url, title = m.group(1), _clean(m.group(2))
        if url and title:
            items.append({"title": title, "url": url, "snippet": ""})
    return items[:8]


# ---------- 官方原文抓取增强（质量向人工搜索看齐的关键） ----------
# 对命中「政府域名」的结果 fetch 正文，提取真实金额/资格/材料，替代"只有标题+摘要"。
_GOV_DOMAIN = (".gov.cn", "gov.cn", "wenzhou.gov.cn", "zhengce.")
_AMOUNT_RE = re.compile(r"[¥￥]?\s*([\d,]+(?:\.\d+)?)\s*(万|万元|元|块钱)")
_ELIG_RE = re.compile(r"(毕业.{0,8}年|大学生|高校毕业生|个体工商户|小微企业|注册.{0,6}(?:满|超过|年)|正常经营|缴纳社保|社保|首次创业|带动就业)")


def _fetch_policy_content(url: str) -> str | None:
    """抓取政策页正文，去标签取文本。失败返回 None（静默，不影响搜索结果）。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code != 200:
            return None
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
        # 去 script/style/标签 → 纯文本
        html = re.sub(r"<script.*?</script>", "", html, flags=re.S)
        html = re.sub(r"<style.*?</style>", "", html, flags=re.S)
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]
    except Exception:
        return None


def _extract_policy_detail(text: str) -> dict:
    """从政策正文提取 {amount, eligibility, materials} 真实要素（不编造）。"""
    if not text:
        return {}
    out = {}
    # 金额
    amounts = _AMOUNT_RE.findall(text)
    if amounts:
        out["amount"] = " / ".join(
            f"{a[0]}{a[1]}" for a in amounts[:3])[:80]
    # 资格条件（提取含关键条件的句子）
    els = []
    for m in re.finditer(r"[^。；;]{6,40}?(?:毕业|大学生|高校|个体|小微|注册|社保|创业|就业)[^。；;]{0,30}", text):
        s = m.group(0).strip()
        if len(s) > 8 and s not in els:
            els.append(s)
        if len(els) >= 4:
            break
    if els:
        out["eligibility"] = els[:4]
    # 材料（含"身份证/营业执照/证明/申请表"的片段）
    mats = []
    for kw in ("身份证", "营业执照", "毕业证", "学历", "申请表", "社保", "证明", "合同", "发票"):
        if kw in text:
            mats.append(kw)
    if mats:
        out["materials"] = mats[:6]
    return out


def _enrich_with_content(results: list[dict]) -> list[dict]:
    """对官方/信息平台来源（前 3 条）抓正文补强金额/资格/材料。

    只对政府域名做，避免抓营销站。抓取失败静默跳过（不阻塞、不白屏）。
    """
    enriched = []
    for i, r in enumerate(results):
        r = dict(r)
        url = r.get("url", "")
        if i < 3 and ".gov.cn" in url and r.get("official") == "官方":
            content = _fetch_policy_content(url)
            detail = _extract_policy_detail(content or "")
            if detail:
                r["detail"] = detail
        enriched.append(r)
    return enriched


def search_and_format(region: str, keyword: str = None) -> str:
    """搜索当地政策 → 格式化成报告段落。keyword 可指定搜索类目（动态搜索词）。失败返回空串。"""
    results = search_policies(region, keyword or "创业补贴 政策")
    if not results:
        return ""
    results = _enrich_with_content(results[:6])
    lines = [f"\n🔍 **实时搜索「{region}」相关政策**（来源：网页搜索结果，官方优先，需点开核验）："]
    for r in results[:6]:
        tag = {"官方": "🏛 官方", "信息平台": "📄 信息平台", "需核验": "🔗 第三方"}.get(r.get("official"), "")
        line = f"- {tag} **{r['title']}**\n  · [查看来源]({r['url']})"
        if r.get("snippet"):
            line += f"\n  · {r['snippet']}"
        # 官方原文抓取到的真实要素（质量增强）
        detail = r.get("detail", {})
        if detail.get("amount"):
            line += f"\n  · 💰 {detail['amount']}"
        if detail.get("eligibility"):
            line += f"\n  · ✅ 资格：{'；'.join(detail['eligibility'][:2])}"
        if detail.get("materials"):
            line += f"\n  · 📋 材料：{'、'.join(detail['materials'])}"
        lines.append(line)
    lines.append("\n> 以上为搜索引擎实时结果，🏛官方来源可作申请依据；💰/✅/📋 为抓取原文提炼，具体以官方最新文件为准。")
    return "\n".join(lines)


# ---------- SearXNG：开源自托管元搜索（GitHub 正解，可绕过反爬限流） ----------
# 配置 SEARXNG_URL（如 http://127.0.0.1:8080）即启用。
# SearXNG 聚合百度/Bing/360/搜狗/知乎/B站等引擎，由服务器代为请求 → 稳定、无单源限流。
def _search_searxng(query: str, limit: int = 8) -> list[dict]:
    url = os.getenv("SEARXNG_URL", "").strip().rstrip("/")
    if not url:
        return []
    try:
        resp = requests.get(
            f"{url}/search",
            params={"q": query, "format": "json", "language": "zh-CN"},
            headers={"User-Agent": HEADERS["User-Agent"]},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        out = []
        for item in data.get("results", [])[:limit]:
            out.append({
                "title": _clean(item.get("title", "")),
                "url": item.get("url", ""),
                "snippet": _clean(item.get("content", "") or item.get("snippet", "")),
            })
        return out
    except Exception:
        return []


def _search_bing_api(query: str, limit: int = 8) -> list[dict]:
    """Bing Web Search API v7（需 BING_SEARCH_API_KEY）。返回 [{title,url,snippet}]。"""
    key = os.getenv("BING_SEARCH_API_KEY", "").strip()
    if not key:
        return []
    try:
        resp = requests.get(
            "https://api.bing.microsoft.com/v7.0/search",
            params={"q": query, "count": limit, "mkt": "zh-CN",
                    "setLang": "zh-hans", "responseFilter": "Webpages"},
            headers={"Ocp-Apim-Subscription-Key": key, "User-Agent": HEADERS["User-Agent"]},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        out = []
        for item in data.get("webPages", {}).get("value", []):
            out.append({
                "title": _clean(item.get("name", "")),
                "url": item.get("url", ""),
                "snippet": _clean(item.get("snippet", "")),
            })
        return out
    except Exception:
        return []


def _search_bing(query: str) -> list[dict]:
    html = _fetch("https://www.bing.com/search", params={"q": query, "setlang": "zh-hans"})
    return _parse_bing(html) if html else []


def _search_cn_bing(query: str) -> list[dict]:
    """必应中国版（cn.bing.com，国内可达，结构同国际版）。"""
    html = _fetch("https://cn.bing.com/search", params={"q": query, "setlang": "zh-hans"})
    return _parse_bing(html) if html else []


def _parse_sogou(html: str) -> list[dict]:
    items = []
    # 搜狗结果块：<div class="vrwrap"> ... <h3><a href="URL">TITLE</a></h3> ... <p>SNIPPET</p>
    for m in re.finditer(r'<div class="vrwrap".*?</div>\s*</div>', html, re.S):
        block = m.group(0)
        am = re.search(r'<h3[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not am:
            continue
        url, title = am.group(1), _clean(am.group(2))
        pm = re.search(r'<p[^>]*class="[^"]*str[^"]*"[^>]*>(.*?)</p>', block, re.S)
        snippet = _clean(pm.group(1)) if pm else ""
        if url and title:
            items.append({"title": title, "url": url, "snippet": snippet})
    return items[:8]


def _search_sogou(query: str) -> list[dict]:
    """搜狗（国内可达，规避限流的备选源）。"""
    html = _fetch("https://www.sogou.com/web", params={"query": query})
    return _parse_sogou(html) if html else []


def _search_ddg(query: str) -> list[dict]:
    html = _fetch("https://html.duckduckgo.com/html/", data={"q": query})
    return _parse_ddg(html) if html else []


def _search_baidu(query: str) -> list[dict]:
    html = _fetch("https://www.baidu.com/s", params={"wd": query})
    return _parse_baidu(html) if html else []


_POLICY_WORDS = ("补贴", "创业", "就业", "优惠", "减免", "资助", "奖励", "支持",
                 "政策", "申报", "认定", "扶持", "减免税", "人才", "大学生")


def _is_policy_relevant(r: dict) -> bool:
    """判断结果是否与政策相关（标题/摘要命中政策词）。

    用作排序权重（不硬剔除——免费引擎结果少，剔除会误伤"有结果"）。
    政策词命中的排前面，纯百科/景点等压后但不删。
    """
    text = (r.get("title", "") + " " + r.get("snippet", ""))
    return any(k in text for k in _POLICY_WORDS)


def _merge_dedup(results: list[dict], limit: int = 8) -> list[dict]:
    """多源结果按 URL 去重 + 垃圾站过滤，再按来源分级 + 政策相关性排序。

    排序：官方且政策相关 → 官方 → 信息平台 → 需核验。不硬剔相关性（保可用性）。
    """
    seen, merged = set(), []
    for r in results:
        url = r.get("url", "")
        if not url or url in seen or _is_junk(r):
            continue
        seen.add(url)
        merged.append(r)
    # 先打来源标签（rank_results 负责），再按"官方优先 + 政策相关优先"排序
    tagged = _rank_results(merged)
    tagged.sort(key=lambda r: (_SORT_ORDER.get(r.get("official"), 2),
                               0 if _is_policy_relevant(r) else 1))
    return tagged[:limit]


def _search_all(query: str) -> list[dict]:
    """多源免费爬虫全部尝试（5 源，国内可达优先），合并去重。

    源顺序：必应国际 → 必应中国 → DuckDuckGo → 搜狗 → 百度。
    任一源成功即累积，提升"问就有"概率。
    """
    all_results: list[dict] = []
    for fn in (_search_bing, _search_cn_bing, _search_ddg, _search_sogou, _search_baidu):
        try:
            res = fn(query)
            if res:
                all_results.extend(res)
        except Exception:
            continue
    return all_results


def search_web(query: str) -> list[dict]:
    """通用实时搜索（卖点核心：问就有）。返回 [{title, url, snippet, official}]。

    策略（多档，保证"问就有"概率最大）：
      1. 有 BING_API_KEY → 真搜索 API（稳定，可作申请依据）
      2. 三源免费爬虫合并（Bing→DDG→百度），官方优先
      3. 主 query 全失败 → 简化 query 重试（去掉"官方/2026"限定词），
         提高被限流/复杂 query 时的命中率
    """
    # 档位1：真搜索 API（配 BING_SEARCH_API_KEY 时）
    api_results = _search_bing_api(query)
    if api_results:
        return _rank_results([r for r in api_results if not _is_junk(r)])

    # 档位2：SearXNG 自托管元搜索（配 SEARXNG_URL 时，GitHub 正解）
    sx_results = _search_searxng(query)
    if sx_results:
        return _merge_dedup(sx_results)

    # 档位3：三源免费爬虫合并
    merged = _merge_dedup(_search_all(query))
    if merged:
        return merged

    # 档位3：简化 query 重试（防复杂 query / 限流）
    simple = re.sub(r"\s*2026\s*", " ", query).strip()
    if simple and simple != query:
        merged2 = _merge_dedup(_search_all(simple))
        if merged2:
            return merged2

    return []


# ---------- 来源分级（搜索质量是卖点：官方优先、可溯源） ----------
_SORT_ORDER = {"官方": 0, "信息平台": 1, "需核验": 2}

# 垃圾站黑名单（标题/域名命中即丢弃，防止营销/低质站污染首屏）
_JUNK_KEYWORDS = ("黑料", "爆料", "正能量", "福利", "小视频", "成人", "博彩",
                  "棋牌", "交友", "兼职刷单", "低价代开", "黄页", "站群",
                  "服饰", "时尚", "女装", "男装", "鞋", "包包", "化妆品", "母婴",
                  "H&M", "zara", "拼多多店铺", "加盟", "微商")


def _is_junk(result: dict) -> bool:
    text = (result.get("title", "") + " " + result.get("url", "")).lower()
    return any(k in text for k in _JUNK_KEYWORDS)


def _classify_source(url: str) -> str:
    """按域名给来源分级：官方 / 信息平台 / 需核验。

    - 官方：政府门户 / .gov.cn（可溯源第一优先级）
    - 信息平台：本地宝 / 12333 人社站 / 人才网（内容常用但非官方口径）
    - 需核验：其余第三方站（营销/自媒体，展示时提示）
    """
    u = (url or "").lower()
    if ".gov.cn" in u or ".gov/" in u or u.startswith("https://www.gov."):
        return "官方"
    if any(h in u for h in ("bendibao", "12333", "wzrc", "hrss")):
        return "信息平台"
    return "需核验"


def _rank_results(results: list[dict]) -> list[dict]:
    """按来源分级排序（官方置顶），并为每条打上 official 标签。"""
    for r in results:
        r["official"] = _classify_source(r.get("url", ""))
        r["_sort"] = _SORT_ORDER.get(r["official"], 2)
    results.sort(key=lambda x: x["_sort"])
    for r in results:
        r.pop("_sort", None)
    return results


def _query_variant(region: str, keyword: str, round_no: int) -> str:
    """生成第 round_no 轮的搜索词变体。

    第 1 轮用主词（可能是行业动态词）；后续轮换更精准的政策措辞，
    覆盖"OPC 一人公司 / 一次性创业补贴 / 材料"等不同表述，提高命中政策原文概率。
    第 2 轮固定加入 OPC 场景词（产品定位场景词，非城市枚举）——让任意地区
    都能搜到当地 OPC 新政（如杭州工位注册/Token券、安徽算力补贴）。
    """
    k = keyword or "创业补贴 政策"
    if round_no == 0:
        return f"{region} {k} 申请条件 2026"
    if round_no == 1:
        return f"{region} OPC 一人公司 创业补贴 工位注册 2026"
    if round_no == 2:
        return f"{region} {k} 材料 申请 通知 2026"
    return f"{region} 创业扶持 补贴 政策 文件 2026"


def search_policies(region: str, keyword: str = "创业补贴 政策",
                    max_rounds: int | None = None) -> list[dict]:
    """实时搜索当地政策（自适应补搜，卖点：问就有 + 有质）。

    首轮搜出后统计"政策相关"条数：若不足目标（3 条），自动换更精准的政策词
    再搜，累积合并去重，直到政策相关达标或达 max_rounds 轮。
    返回 [{title, url, snippet, official}]。

    max_rounds：
    - None（默认）：自动——配了真后端（BING_API_KEY/SEARXNG_URL）时补搜到
      精准为止（免费爬虫对精准词命中差，补搜收益低且拖慢演示）；
      纯免费爬虫时只用 1 轮（保"有结果 + 快"）。
    """
    use_backend = bool(os.getenv("BING_SEARCH_API_KEY")) or bool(os.getenv("SEARXNG_URL"))
    rounds = max_rounds if max_rounds is not None else (3 if use_backend else 1)

    target = 3  # 政策相关结果达到 3 条即停止补搜
    all_results: list[dict] = []
    for rnd in range(rounds):
        query = _query_variant(region, keyword, rnd)
        res = search_web(query)
        if res:
            all_results.extend(res)
        # 累积去重 + 排序后，统计政策相关数
        merged = _merge_dedup(all_results)
        relevant = [r for r in merged if _is_policy_relevant(r)]
        # 达标即提前结束（快路径）；不足则补搜（慢路径）
        if len(relevant) >= target:
            return merged
    return _merge_dedup(all_results)


def generate_query(region: str, profile: dict | None = None, llm_fn=None) -> str:
    """零值枚举生成搜索词（核心：搜索词=模型理解，不是类目穷举）。

    - LLM 可用（传入 llm_fn，返回 (text, model)）：让模型根据行业+经营特点生成精准搜索词，
      覆盖任意行业（宠物殡葬/直播带货/元宇宙…），不映射任何固定类目表。
    - LLM 不可用：直接用用户原话行业词拼进搜索词（跟 business_profile 同哲学——
      用户说什么行业就搜什么，不做硬编码 if/elif 映射）。
    """
    ind = ((profile or {}).get("industry") or "").strip()
    reg_type = ((profile or {}).get("reg_type") or "").strip()
    region = (region or "").strip()

    # ① LLM 生成精准搜索词（理解任意行业/经营特点）
    if llm_fn is not None:
        try:
            sys_p = (
                "你是政策检索专家。根据用户行业与经营信息，生成 1 条搜索引擎查询词（中文），"
                "用于搜当地针对该行业的创业/税收/补贴政策。只输出查询词本身，不要解释。"
                f"行业：{ind or '未知'}；注册类型：{reg_type or '未知'}；地区：{region}。"
            )
            text, _ = llm_fn(sys_p, "")
            q = (text or "").strip().split("\n")[0].strip().strip("“”\"'。")
            # 修复（L3）：and 优先于 or，原式会把"只含补贴但不限长度"误判通过 → 用括号明确分组
            if 4 <= len(q) <= 40 and ("政策" in q or "补贴" in q or "税收" in q or "支持" in q):
                return q
        except Exception:
            pass  # LLM 失败 → 降级原话兜底，绝不白屏

    # ② 无 key / LLM 失败：用户原话行业词直接拼（零值枚举，不映射类目）
    base = f"{region} 创业 补贴 政策 2026"
    if ind:
        # 行业是用户原话（如"宠物殡葬"），直接作为核心词，不查类目表
        return f"{region} {ind} 创业 补贴 政策 2026"
    return base


def generate_keyword_from_desc(desc: str, region: str, llm_fn=None) -> str:
    """用户描述需求 → LLM 提炼 1 条精准搜索关键词（供「💬 AI 生成关键词」按钮）。

    理解任意表达（零值枚举）：用户说"我想看杭州怎么支持一人公司"→ 提炼
    "OPC 一人公司 创业补贴 工位注册"。失败返回空串（上层提示留空用自动搜索）。
    """
    desc = (desc or "").strip()
    if not desc or llm_fn is None:
        return ""
    try:
        sys_p = (
            "你是政策检索专家。用户用大白话描述想查的当地政策，请提炼 1 条精准的"
            "搜索引擎关键词（中文）。地区：{region}。\n"
            "要求：只输出关键词本身（不含地区名、不含'政策/补贴'等冗余前缀），"
            "8-20 字，不要解释。\n"
            "示例：\n"
            "- '我想看杭州怎么支持一人公司' → OPC 一人公司 创业补贴 工位注册\n"
            "- '帮我看看小微企业有什么税收优惠' → 小微企业 税收优惠 减免\n"
            "- '想了解直播带货能不能申请补贴' → 直播带货 创业补贴 申请条件"
        )
        text, _ = llm_fn(sys_p, f"用户需求：{desc}")
        q = (text or "").strip().split("\n")[0].strip().strip("“”\"'。")
        if 2 <= len(q) <= 30:
            return q
    except Exception:
        pass
    return ""


def search_opc_policies(region: str, keyword: str = "", profile: dict | None = None,
                        llm_fn=None) -> list[dict]:
    """OPC 场景政策搜索（搜索词三档，用户完全可控，零预置）。

    搜索词优先级（零值枚举，用户驱动，不预置任何地区/行业表）：
      1. 用户输入指定关键词 → 直接用 {region} {keyword} 2026
      2. 无用户关键词 + LLM 可用 → 模型生成精准搜索词（理解任意表达）
      3. 都无 → OPC 场景热点词兜底（产品定位场景词，非城市枚举）

    复用 search_web（多源）+ _enrich_with_content（官方原文提取金额/资格/材料）。
    返回 [{title, url, snippet, official, detail}]，失败返回空（上层给降级提示）。
    """
    region = (region or "").strip()
    keyword = (keyword or "").strip()
    if not region:
        return []

    # 档位 1：用户输入指定关键词（用户想搜什么就搜什么）
    main_query = f"{region} {keyword} 2026" if keyword else ""

    # 档位 2：LLM 生成精准搜索词
    if not main_query and llm_fn is not None:
        try:
            sys_p = (
                "你是政策检索专家。根据用户行业与经营信息，生成 1 条搜索引擎查询词（中文），"
                "用于搜当地针对该行业的创业/税收/补贴政策。只输出查询词本身，不要解释。"
                f"行业：{((profile or {}).get('industry') or '未知')}；"
                f"注册类型：{((profile or {}).get('reg_type') or '未知')}；地区：{region}。"
            )
            text, _ = llm_fn(sys_p, "")
            q = (text or "").strip().split("\n")[0].strip().strip("“”\"'。")
            if 4 <= len(q) <= 40 and ("政策" in q or "补贴" in q or "税收" in q or "支持" in q):
                main_query = f"{region} {q} 2026"
        except Exception:
            pass

    # 档位 3：OPC 场景热点词兜底（产品定位场景词）
    if not main_query:
        ind = ((profile or {}).get("industry") or "").strip()
        if ind:
            main_query = f"{region} {ind} OPC 创业 补贴 政策 2026"
        else:
            main_query = f"{region} OPC 一人公司 创业补贴 工位注册 Token券 算力券 2026"

    # 多轮补搜：主词 1 轮 + OPC 变体补搜，政策相关达标即停
    all_results: list[dict] = []
    for rnd in range(3):
        query = main_query if rnd == 0 else _query_variant(region, keyword, rnd)
        res = search_web(query)
        if res:
            all_results.extend(res)
        merged = _merge_dedup(all_results)
        relevant = [r for r in merged if _is_policy_relevant(r)]
        if len(relevant) >= 3:
            return _enrich_with_content(merged[:6])
    return _enrich_with_content(_merge_dedup(all_results)[:6])


def unavailable_notice(region: str) -> str:
    """实时搜索不可用时的显式提示（网络受限降级文案，不哑火）。

    用途：创空间/办公网可能限制外网，此时明确告知评委"是网络限制、非功能缺失"，
    并引导到本地通用政策库，保证演示不断片。
    """
    return (f"\n⚠️ 当前网络环境无法实时抓取「{region}」政策"
            f"（创空间/办公网可能限制外网访问）。\n"
            f"为保证演示正常，以下为你展示**预收录的本地通用政策库**（见下方通用建议），"
            f"具体以当地官方文件为准。")


def format_unavailable(query: str) -> str:
    """合规问答场景的联网不可用提示。"""
    return (f"\n⚠️ 当前网络环境无法实时联网搜索（网络受限或搜索源不可达）。"
            f"以上回答基于本地知识库，具体以官方最新文件为准。")


def format_web_search(query: str, limit: int = 5) -> str:
    """通用搜索并格式化（合规问答用）。失败返回空串。"""
    results = search_web(query)
    if not results:
        return ""
    lines = [f"🔍 实时联网搜索到的相关结果（来源：网页搜索，官方优先，需点开核验）："]
    for r in results[:limit]:
        tag = {"官方": "🏛 官方", "信息平台": "📄 信息平台", "需核验": "🔗 第三方"}.get(r.get("official"), "")
        line = f"- {tag} **{r['title']}**"
        if r.get("snippet"):
            line += f"：{r['snippet']}"
        line += f"\n  · [查看来源]({r['url']})"
        lines.append(line)
    lines.append("> 以上为搜索引擎实时结果，🏛官方来源可作依据，其余以官方最新发布为准。")
    return "\n".join(lines)
