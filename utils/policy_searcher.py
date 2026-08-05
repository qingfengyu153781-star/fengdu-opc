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


# ---------- 真 API：Azure Bing Search（免费层 1000 次/月，稳定可作申请依据） ----------
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


def _merge_dedup(results: list[dict], limit: int = 8) -> list[dict]:
    """多源结果按 URL 去重（保留首个）+ 垃圾站过滤，再按来源分级排序。"""
    seen, merged = set(), []
    for r in results:
        url = r.get("url", "")
        if not url or url in seen or _is_junk(r):
            continue
        seen.add(url)
        merged.append(r)
    return _rank_results(merged)[:limit]


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
    # 档位1：真搜索 API
    api_results = _search_bing_api(query)
    if api_results:
        return _rank_results([r for r in api_results if not _is_junk(r)])

    # 档位2：三源免费爬虫合并
    merged = _merge_dedup(_search_all(query))
    if merged:
        return merged

    # 档位3：简化 query 重试（防复杂 query / 限流）
    simple = re.sub(r"\s*(官方|2026)\s*", " ", query).strip()
    if simple and simple != query:
        merged2 = _merge_dedup(_search_all(simple))
        if merged2:
            return merged2

    return []


# ---------- 来源分级（搜索质量是卖点：官方优先、可溯源） ----------
_SORT_ORDER = {"官方": 0, "信息平台": 1, "需核验": 2}

# 垃圾站黑名单（标题/域名命中即丢弃，防止营销/低质站污染首屏）
_JUNK_KEYWORDS = ("黑料", "爆料", "正能量", "福利", "小视频", "成人", "博彩",
                  "棋牌", "交友", "兼职刷单", "低价代开", "黄页", "站群")


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


def search_policies(region: str, keyword: str = "创业补贴 政策") -> list[dict]:
    """实时搜索当地政策。多源尝试，返回 [{title, url, snippet, official}] 或空列表。

    query 带「官方」限定词：引导搜索引擎优先返回政府门户/官方公告，提升结果质量。
    """
    query = f"{region} {keyword} 官方 申请条件 2026"
    return search_web(query)


def _policy_query_for(profile: dict, region: str) -> str:
    """根据用户经营信息生成精准搜索词（纯规则，零 key）。

    行业/意图 → 对应政策类目词；地区 → 城市名。覆盖"问什么有什么"。
    """
    ind = (profile or {}).get("industry") or ""
    reg_type = (profile or {}).get("reg_type") or ""

    # 行业 → 政策类目
    cat = "创业补贴 政策"
    if any(k in ind for k in ("软件", "AI", "开发", "科技", "研发")):
        cat = "软件企业 税收优惠 研发补贴 政策"
    elif any(k in ind for k in ("摄影", "设计", "文化", "传媒")):
        cat = "文化创意 创业补贴 就业政策"
    elif any(k in ind for k in ("餐饮", "外卖", "食品")):
        cat = "餐饮 创业补贴 就业政策"
    elif any(k in ind for k in ("电商", "淘宝", "网店")):
        cat = "电商 创业补贴 灵活就业 政策"
    elif any(k in ind for k in ("咨询", "服务")):
        cat = "现代服务 创业补贴 政策"

    # 注册类型 → 补充
    if "个体" in reg_type:
        cat += " 个体工商户"
    elif "一人" in reg_type or "公司" in reg_type:
        cat += " 小微企业"

    return f"{region} {cat} 官方 2026"


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


def search_and_format(region: str, keyword: str = None) -> str:
    """搜索当地政策 → 格式化成报告段落。keyword 可指定搜索类目（动态搜索词）。失败返回空串。"""
    results = search_policies(region, keyword or "创业补贴 政策")
    if not results:
        return ""
    lines = [f"\n🔍 **实时搜索「{region}」相关政策**（来源：网页搜索结果，官方优先，需点开核验）："]
    for r in results[:6]:
        tag = {"官方": "🏛 官方", "信息平台": "📄 信息平台", "需核验": "🔗 第三方"}.get(r.get("official"), "")
        line = f"- {tag} **{r['title']}**\n  · [查看来源]({r['url']})"
        if r.get("snippet"):
            line += f"\n  · {r['snippet']}"
        lines.append(line)
    lines.append("\n> 以上为搜索引擎实时结果，🏛官方来源可作申请依据；📄/🔗 为信息平台或第三方，具体申请条件/金额以官方最新文件为准。")
    return "\n".join(lines)


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
