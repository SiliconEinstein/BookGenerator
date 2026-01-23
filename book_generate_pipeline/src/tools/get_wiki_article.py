import os
import re
import aiohttp
from typing import Dict, Any, Optional, List, Union

WIKI_SEARCH_API_BASE = "https://literature-sage.test.bohrium.com"


async def search_wiki_articles_for_subchapter(
        subchapter_title: str,
        topics: List[str],
        k: int = 5,
        language: str = "zh-CN",
    ) -> Union[List[str], tuple]:
        """Search wiki articles based on subchapter title and topics."""
        url = f"{WIKI_SEARCH_API_BASE}/api/v1/wiki_v2/article/hybrid"
        k = min(k, 5)
        if k <= 0:
            k = 5

        all_search_items = topics + [subchapter_title]
        articles_content: List[str] = []
        seen_ids = set()
        seen_keywords = set()
        article_titles = []

        for search_item in all_search_items:
            def _extract_single_keyword(text: str) -> List[str]:
                keywords = set()
                segments = re.split(r'[与和]', text)
                for segment in segments:
                    segment = segment.strip()
                    if segment and len(segment) >= 2 and segment not in seen_keywords:
                        keywords.add(segment)
                        seen_keywords.add(segment)
                if not keywords and len(text) < 8 and text.strip():
                    keywords.add(text.strip())
                return keywords

            keywords = _extract_single_keyword(search_item)
            final_keywords = {kw: 1.0 for kw in keywords}
            if not keywords:
                continue

            headers = {"Content-Type": "application/json"}
            payload = {
                "text": search_item or "",
                "keywords": final_keywords,
                "k": 1,
                "language": language or "zh-CN",
                "include_content": True,
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers,
                                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
            except Exception:
                continue

            raw_list: List[Dict[str, Any]] = []
            try:
                if isinstance(data, dict):
                    arr = None
                    if isinstance(data.get("data"), list):
                        arr = data.get("data")
                    elif isinstance(data.get("data"), dict):
                        dd = data.get("data")
                        if isinstance(dd.get("items"), list):
                            arr = dd.get("items")
                        elif isinstance(dd.get("results"), list):
                            arr = dd.get("results")
                        elif isinstance(dd.get("result"), list):
                            arr = dd.get("result")
                    elif isinstance(data.get("results"), list):
                        arr = data.get("results")
                    if isinstance(arr, list):
                        raw_list = arr
            except Exception:
                raw_list = []

            for r in raw_list:
                if not isinstance(r, dict):
                    continue
                aid = r.get("article_id") or r.get("articleId") or r.get("id")
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)

                title = r.get("title") or r.get("article_title") or r.get("article_name") or r.get("name") or ""
                main_content = r.get("main_content", "")
                applications = r.get("applications", "")

                content_parts = []
                if title:
                    content_parts.append(str(title))
                if main_content:
                    content_parts.append(str(main_content))
                if applications:
                    content_parts.append(str(applications))

                if content_parts:
                    full_content = "\n".join(content_parts)
                    pattern = r"\(@[^:]+:[^)]*\)"
                    clean_content = re.sub(pattern, "", full_content)
                    articles_content.append(clean_content)
                    article_titles.append(title)
                    if len(articles_content) >= k:
                        print(f"Got {len(articles_content)} articles: {article_titles}")
                        return articles_content[:k], article_titles[:k]


        print(f"Got {len(articles_content)} articles: {article_titles}")
        return articles_content[:k], article_titles[:k]