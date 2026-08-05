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
    """通用实时搜索。多源尝试，返回 [{title, url, snippet}] 或空列表。"""
    for fn in (_search_bing, _search_ddg, _search_baidu):
        try:
            res = fn(query)
            if res:
                return res
        except Exception:
            continue
    return []


def search_policies(region: str, keyword: str = "创业补贴 政策") -> list[dict]:
    """实时搜索当地政策。多源尝试，返回 [{title, url, snippet}] 或空列表。"""
    query = f"{region} {keyword} 申请条件 2026"
    return search_web(query)


def search_and_format(region: str) -> str:
    """搜索当地政策 → 格式化成报告段落。失败返回空串。"""
    results = search_policies(region)
    if not results:
        return ""
    lines = [f"\n🔍 **实时搜索「{region}」相关政策**（来源：网页搜索结果，需点开核验）："]
    for r in results[:6]:
        line = f"- **{r['title']}**\n  · [查看来源]({r['url']})"
        if r.get("snippet"):
            line += f"\n  · {r['snippet']}"
        lines.append(line)
    lines.append("\n> 以上为搜索引擎实时结果，具体申请条件/金额以官方最新文件为准。")
    return "\n".join(lines)


def format_web_search(query: str, limit: int = 5) -> str:
    """通用搜索并格式化（合规问答用）。失败返回空串。"""
    results = search_web(query)
    if not results:
        return ""
    lines = [f"🔍 实时联网搜索到的相关结果（来源：网页搜索，需点开核验）："]
    for r in results[:limit]:
        line = f"- **{r['title']}**"
        if r.get("snippet"):
            line += f"：{r['snippet']}"
        line += f"\n  · [查看来源]({r['url']})"
        lines.append(line)
    lines.append("> 以上为搜索引擎实时结果，以官方最新发布为准。")
    return "\n".join(lines)
