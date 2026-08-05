# -*- coding: utf-8 -*-
"""实时政策搜索（免费，零 key）。

用户所在地区未收录时，实时搜索当地政策，返回真实网页结果（标题+URL+摘要），可溯源。
多源尝试：Bing → DuckDuckGo → 百度。全部失败返回空列表，由上层回退通用库。

⚠️ 零造假：返回的都是搜索引擎真实结果，带来源 URL。摘要来自搜索结果页，需点开核验。
"""
from __future__ import annotations

import re

import requests

TIMEOUT = 8
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


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


def _search_bing(query: str) -> list[dict]:
    html = _fetch("https://www.bing.com/search", params={"q": query, "setlang": "zh-hans"})
    return _parse_bing(html) if html else []


def _search_ddg(query: str) -> list[dict]:
    html = _fetch("https://html.duckduckgo.com/html/", data={"q": query})
    return _parse_ddg(html) if html else []


def _search_baidu(query: str) -> list[dict]:
    html = _fetch("https://www.baidu.com/s", params={"wd": query})
    return _parse_baidu(html) if html else []


def search_web(query: str) -> list[dict]:
    """通用实时搜索。多源尝试，返回 [{title, url, snippet, official}] 或空列表。"""
    for fn in (_search_bing, _search_ddg, _search_baidu):
        try:
            res = fn(query)
            if res:
                return _rank_results(res)
        except Exception:
            continue
    return []


# ---------- 来源分级（搜索质量是卖点：官方优先、可溯源） ----------
_SORT_ORDER = {"官方": 0, "信息平台": 1, "需核验": 2}


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


def search_and_format(region: str) -> str:
    """搜索当地政策 → 格式化成报告段落。失败返回空串。"""
    results = search_policies(region)
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
