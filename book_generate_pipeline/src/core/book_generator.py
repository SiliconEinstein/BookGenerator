"""Book generator for creating educational content chapters."""

import os
import re
import json
import asyncio
import aiohttp
from fastmcp import Client
from typing import Dict, Any, Optional, List, Union
from src.models import gemini_completion, gpt_completion
from src.utils import get_config, sanitize_filename
from src.tools import search_wiki_articles_for_subchapter, search_qa_pairs_for_subchapter


PROMPT_ABSTRACT = "prompt_abstract"
PROMPT_BOOK = "prompt_book"
PROMPT_BOOK_STEP2 = "prompt_book_step2"
PROMPT_BOOK_STEP3 = "prompt_book_step3"
WIKI_SEARCH_API_BASE = "https://literature-sage.test.bohrium.com"


class BookGenerator:
    """Generates book content including abstracts, sections, and chapters."""

    def __init__(self, language: str = "ch"):
        self.language = language
        self.config = get_config(language=language)
        self.mcp_url = self.config.mcp_url
        self.wiki_search_api_base = self.config.wiki_search_api_base

    async def generate_abstract(self, sub_title: str, topics: List[str], course_name: str,
                              sub_code: str, structure_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Generate chapter outline summary."""
        topics_str = ", ".join(topics)

        # 获取Pedia文章（注释）
        wiki_articles_content, wiki_titles = await search_wiki_articles_for_subchapter(
            subchapter_title=sub_title,
            topics=topics,
            k=5,
            language="zh-CN" if self.language == 'ch' else "en-US",
        )
        wiki_content_str = "\n\n".join(wiki_articles_content) if wiki_articles_content else "No related wiki articles found."

        # 获取问答对
        # qa_result = await search_qa_pairs_for_subchapter(
        #     subchapter_title=sub_title,
        #     topics=topics,
        #     max_keywords=10,
        #     max_results_per_keyword=1
        # )
        
        # qa_pairs = qa_result.get("qa_pairs", [])
        # qa_content_list = []
        # for qa in qa_pairs:
        #     problem_thumbnail = qa.get("problem_thumbnail", "")
        #     problem = qa.get("problem", "")
        #     solutions = qa.get("solutions", "")
            
        #     qa_text = f"title: {problem_thumbnail}\n\nQuestion: {problem}\n\nAnswer: {solutions}"
        #     qa_content_list.append(qa_text)
        
        # wiki_content_str = "\n\n\n".join(qa_content_list) if qa_content_list else "No related QA pairs found."
        
        prompt_path = self.config.get_prompt_path(PROMPT_ABSTRACT)
        prompt = self._read_file_safe(prompt_path)
        prompt = prompt.format(
            course_name=course_name,
            subchapter_code=sub_code,
            subchapter_title=sub_title,
            topics=topics_str,
            wiki_content=wiki_content_str,
            structure_summary=structure_summary
        )

        abstract = await gpt_completion(prompt)
        return {"abstract": abstract, "wiki_content": wiki_content_str}

    async def generate_content(self, sub_title: str, topics: List[str], course_name: str,
                             sub_code: str, structure_summary: Dict[str, Any],
                             chapter_abstracts: Dict[str, str],
                             wiki_content: Optional[str] = None) -> str:
        """Generate textbook content."""
        topics_str = ", ".join(topics)

        # 如果没有提供 wiki_content，则调用接口获取
        if wiki_content is None:
            wiki_articles_content, wiki_titles = await search_wiki_articles_for_subchapter(
                subchapter_title=sub_title,
                topics=topics,
                k=5,
                language="zh-CN" if self.language == 'ch' else "en-US",
            )
            wiki_content_str = "\n\n".join(wiki_articles_content) if wiki_articles_content else "No related wiki articles found."
        else:
            wiki_content_str = wiki_content

        abstracts_str = "\n\n".join(
            f"### 子章节 {sc}: {abst}"
            for sc, abst in chapter_abstracts.items()
        )

        prompt_path = self.config.get_prompt_path(PROMPT_BOOK)
        prompt = self._read_file_safe(prompt_path)
        prompt = prompt.format(
            course_name=course_name,
            subchapter_code=sub_code,
            subchapter_title=sub_title,
            topics=topics_str,
            wiki_content=wiki_content_str,
            structure_summary=structure_summary,
            chapter_abstracts=abstracts_str
        )

        norm_language = "Chinese" if self.language == 'ch' else "English"
        article_content = None
        for i in range(3):
            try:
                article_content = await self._generate_section_with_content(
                    topic=sub_title,
                    style_guide=prompt,
                    language=norm_language,
                    mode="advanced",
                )
                if article_content:
                    print(f"[Info] Attempt {i+1} succeeded for subchapter {sub_code}")
                    break
            except Exception as e:
                print(f"[Error] Attempt {i+1} failed for subchapter {sub_code}: {e}")

        return article_content or ""

    async def insert_project(self, course_name: str, chapter_title: str,
                            chapter_structure: Dict[str, Any], sub_chapters: Dict[str, Any],
                            subchapter_file_paths: Dict[str, str]) -> tuple:
        """Enhance chapter cohesion and insert projects as线索."""
        chapter_content_parts = []
        for sub_code, sub_info in sub_chapters.items():
            sub_title = sub_info['subchapter_title']
            input_path = subchapter_file_paths.get(sub_code)
            if os.path.exists(input_path):
                with open(input_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                chapter_content_parts.append(f"## {sub_code} {sub_title}\n{content}")
            else:
                print(f"  [Warning] File not found: {input_path}")

        chapter_content = "\n\n".join(chapter_content_parts)

        prompt_path = self.config.get_prompt_path(PROMPT_BOOK_STEP2)
        prompt = self._read_file_safe(prompt_path)
        prompt = prompt.format(
            course_name=course_name,
            chapter_title=chapter_title,
            chapter_structure=chapter_structure,
            chapter_content=chapter_content
        )
        new_chapter_content = await gemini_completion(prompt)
        print(f"{chapter_title}：Old chapter length {len(chapter_content)}. New chapter length {len(new_chapter_content)}")

        # Check for syntax, format errors, and hallucinations
        prompt_check_path = self.config.get_prompt_path(PROMPT_BOOK_STEP3)
        prompt_check = self._read_file_safe(prompt_check_path)
        prompt_check = prompt_check.format(
            course_name=course_name,
            chapter_title=chapter_title,
            chapter_structure=chapter_structure,
            chapter_content=new_chapter_content
        )
        print("Starting content check...")
        check_result = await gpt_completion(prompt_check)
        log_match = re.search(r'<log>\s*(.*?)\s*</log>', check_result, re.DOTALL | re.IGNORECASE)
        content_match = re.search(r'<content>\s*(.*?)\s*</content>', check_result, re.DOTALL | re.IGNORECASE)
        log_text = log_match.group(1).strip() if log_match else ""
        checked_chapter_content = content_match.group(1).strip() if content_match else ""
        print(f"Check complete. Checked chapter length: {len(checked_chapter_content)}")

        articles_content = self._decompose_chapter_content(checked_chapter_content)
        return articles_content, checked_chapter_content, log_text

    # async def _search_wiki_articles_for_subchapter(
    #     self,
    #     subchapter_title: str,
    #     topics: List[str],
    #     k: int = 5,
    #     language: str = "zh-CN",
    # ) -> Union[List[str], tuple]:
    #     """Search wiki articles based on subchapter title and topics."""
    #     url = f"{self.wiki_search_api_base}/api/v1/wiki_v2/article/hybrid"
    #     k = min(k, 5)
    #     if k <= 0:
    #         k = 5

    #     all_search_items = topics + [subchapter_title]
    #     articles_content: List[str] = []
    #     seen_ids = set()
    #     seen_keywords = set()
    #     article_titles = []

    #     for search_item in all_search_items:
    #         def _extract_single_keyword(text: str) -> List[str]:
    #             keywords = set()
    #             segments = re.split(r'[与和]', text)
    #             for segment in segments:
    #                 segment = segment.strip()
    #                 if segment and len(segment) >= 2 and segment not in seen_keywords:
    #                     keywords.add(segment)
    #                     seen_keywords.add(segment)
    #             if not keywords and len(text) < 8 and text.strip():
    #                 keywords.add(text.strip())
    #             return keywords

    #         keywords = _extract_single_keyword(search_item)
    #         final_keywords = {kw: 1.0 for kw in keywords}
    #         if not keywords:
    #             continue

    #         headers = {"Content-Type": "application/json"}
    #         payload = {
    #             "text": search_item or "",
    #             "keywords": final_keywords,
    #             "k": 1,
    #             "language": language or "zh-CN",
    #             "include_content": True,
    #         }

    #         try:
    #             async with aiohttp.ClientSession() as session:
    #                 async with session.post(url, json=payload, headers=headers,
    #                                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
    #                     if resp.status != 200:
    #                         continue
    #                     data = await resp.json()
    #         except Exception:
    #             continue

    #         raw_list: List[Dict[str, Any]] = []
    #         try:
    #             if isinstance(data, dict):
    #                 arr = None
    #                 if isinstance(data.get("data"), list):
    #                     arr = data.get("data")
    #                 elif isinstance(data.get("data"), dict):
    #                     dd = data.get("data")
    #                     if isinstance(dd.get("items"), list):
    #                         arr = dd.get("items")
    #                     elif isinstance(dd.get("results"), list):
    #                         arr = dd.get("results")
    #                     elif isinstance(dd.get("result"), list):
    #                         arr = dd.get("result")
    #                 elif isinstance(data.get("results"), list):
    #                     arr = data.get("results")
    #                 if isinstance(arr, list):
    #                     raw_list = arr
    #         except Exception:
    #             raw_list = []

    #         for r in raw_list:
    #             if not isinstance(r, dict):
    #                 continue
    #             aid = r.get("article_id") or r.get("articleId") or r.get("id")
    #             if aid in seen_ids:
    #                 continue
    #             seen_ids.add(aid)

    #             title = r.get("title") or r.get("article_title") or r.get("article_name") or r.get("name") or ""
    #             main_content = r.get("main_content", "")
    #             applications = r.get("applications", "")

    #             content_parts = []
    #             if title:
    #                 content_parts.append(str(title))
    #             if main_content:
    #                 content_parts.append(str(main_content))
    #             if applications:
    #                 content_parts.append(str(applications))

    #             if content_parts:
    #                 full_content = "\n".join(content_parts)
    #                 pattern = r"\(@[^:]+:[^)]*\)"
    #                 clean_content = re.sub(pattern, "", full_content)
    #                 articles_content.append(clean_content)
    #                 article_titles.append(title)
    #                 if len(articles_content) >= k:
    #                     print(f"Got {len(articles_content)} articles: {article_titles}")
    #                     return articles_content[:k], article_titles[:k]


    #     print(f"Got {len(articles_content)} articles: {article_titles}")
    #     return articles_content[:k], article_titles[:k]


    async def _generate_section_with_content(self, topic: str, style_guide: str = None,
                                             language: str = "Chinese", mode: str = "advanced") -> Optional[str]:
        """Call MCP tool to generate article."""
        try:
            async with Client(self.mcp_url) as client:
                print(f"  [API] Requesting generation for: {topic}...")
                result = await client.call_tool("generate_article", {
                    "topic": topic,
                    "language": language,
                    "style_guide": style_guide,
                    "mode": mode,
                })
                try:
                    content_data = json.loads(result.content[0].text)
                    article_content = content_data.get("main_content", "")
                    if article_content == "There are no suffient information in the knowledge base to write the article you required.":
                        print("Generation failed, retrying...")
                        return await self._generate_section_with_content(topic, style_guide, language, mode)
                except (json.JSONDecodeError, AttributeError, IndexError):
                    article_content = result.content[0].text if result.content else ""
                if not article_content:
                    print(f"  [Error] Empty content received for {topic}")
                    return None
                return article_content
        except Exception as e:
            print(f"  [Error] Failed generating section {topic}: {e}")
            return None

    def _decompose_chapter_content(self, full_content: str) -> Dict[str, str]:
        """Decompose full chapter content into sections."""
        results = {}
        lines = full_content.splitlines()
        current_header = None
        current_content_lines = []

        for line in lines[1:]:
            if line.startswith('## ') and not line.startswith('###'):
                if current_header is not None:
                    results[current_header] = '\n'.join(current_content_lines).rstrip()
                current_header = line[2:].strip()
                current_content_lines = [line]
            else:
                if current_header is not None:
                    current_content_lines.append(line)

        if current_header is not None:
            results[current_header] = '\n'.join(current_content_lines).rstrip()
        return results

    def _read_file_safe(self, path: str) -> str:
        """Read file safely."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ""
