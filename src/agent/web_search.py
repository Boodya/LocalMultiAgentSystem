from __future__ import annotations
import re
import time
from typing import List, Dict, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from . import config


def ddg_search(query: str, max_results: int = config.SEARCH_MAX_RESULTS, log=None) -> List[Dict[str, str]]:
    results = []
    if log:
        log(f"ddg query: {query}")
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            # r keys: title, href, body
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
                "source": "text"
            })
    return results


def ddg_news_search(query: str, max_results: int = config.SEARCH_MAX_RESULTS, log=None) -> List[Dict[str, str]]:
    results = []
    if log:
        log(f"ddg news: {query}")
    try:
        with DDGS() as ddgs:
            for r in ddgs.news(query, max_results=max_results):
                # r keys might include: title, url, source, date, body
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("body", ""),
                    "source": r.get("source", "news")
                })
    except Exception as e:
        if log:
            log(f"ddg news error: {e}")
    return results


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        # strip leading www.
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _rank_score(item: Dict[str, str], queries: List[str]) -> int:
    url = item.get("url") or ""
    dom = _domain(url)
    score = 0
    title = (item.get("title") or "").lower()
    snippet = (item.get("snippet") or "").lower()
    text = f"{title} {snippet}"
    # Generic query-term overlap only (no hard-coded keyword biases)
    for q in queries:
        qtoks = re.findall(r"[a-zA-Z0-9]+", q.lower())
        # count up to first 5 tokens overlaps to avoid over-weighting long queries
        overlaps = sum(1 for tok in qtoks[:5] if tok and tok in text)
        score += overlaps
        break
    return score


def fetch_url(url: str, timeout: int = config.REQUEST_TIMEOUT_S) -> Tuple[str, str]:
    headers = {"User-Agent": config.USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        return ("", f"<fetch_error: {e}>")

    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    # Remove scripts/styles
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    text = soup.get_text(" ")
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def google_cse_search(query: str, max_results: int = config.SEARCH_MAX_RESULTS, log=None) -> List[Dict[str, str]]:
    """Google Custom Search JSON API.
    Requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX in config (env vars).
    """
    api_key = config.GOOGLE_CSE_API_KEY
    cx = config.GOOGLE_CSE_CX
    if not api_key or not cx:
        return []
    if log:
        log(f"google cse: {query}")
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(max_results, 10),
        "dateRestrict": getattr(config, "GOOGLE_CSE_DATE_RESTRICT", "d1"),
        "safe": "off",
        "hl": "en"
    }
    try:
        resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=config.REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        out = []
        for it in items:
            out.append({
                "title": it.get("title", ""),
                "url": it.get("link", ""),
                "snippet": it.get("snippet", ""),
                "source": "google"
            })
        return out
    except Exception as e:
        if log:
            log(f"google cse error: {e}")
        return []


def search_and_fetch(queries: List[str], max_results_per_query: int = config.SEARCH_MAX_RESULTS,
                     fetch_max_pages: int = config.FETCH_MAX_PAGES, log=None) -> Dict[str, List[Dict[str, str]]]:
    seen = set()
    aggregated = []
    performed_fallback = False
    # Use only user-provided queries (no curated additions)
    q_all = list(queries)
    for q in q_all:
        if config.SEARCH_PROVIDER == "google" and config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_CX:
            for item in google_cse_search(q, max_results=max_results_per_query, log=log):
                url = item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                aggregated.append(item)
        else:
            # Try News then Text without extra filters
            news_items = ddg_news_search(q, max_results=max_results_per_query, log=log)
            for item in news_items:
                url = item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                aggregated.append(item)
            # Fallback to Text
            text_items = []
            try:
                text_items = ddg_search(q, max_results=max_results_per_query, log=log)
            except Exception as e:
                if log:
                    log(f"ddg text error: {e}")
            for item in text_items:
                url = item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                aggregated.append(item)
    # Rank
    ranked = sorted(aggregated, key=lambda it: _rank_score(it, queries), reverse=True)
    if log:
        for it in ranked[:min(len(ranked), fetch_max_pages)]:
            log(f"rank {it.get('url')} dom={_domain(it.get('url',''))} score={_rank_score(it, queries)}")

    # Fetch top pages
    pages = []
    for item in ranked[:fetch_max_pages]:
        url = item["url"]
        if log:
            log(f"fetch: {url}")
        title, text = fetch_url(url)
        if not text:
            if log:
                log(f"fetch failed: {url}")
            continue
        pages.append({
            "title": title or item.get("title", ""),
            "url": url,
            "snippet": item.get("snippet", ""),
            "content": text[: config.MAX_CONTEXT_DOC_CHARS]
        })
        # be polite
        time.sleep(0.5)
    return {"results": aggregated, "pages": pages}
