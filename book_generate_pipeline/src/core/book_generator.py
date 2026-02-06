"""Book generator for creating educational content chapters."""

import os
import re
import json
import asyncio
import aiohttp
import importlib.util
from fastmcp import Client
from typing import Dict, Any, Optional, List, Union
from src.models import gemini_completion, gpt_completion
from src.utils import get_config, sanitize_filename
from src.tools import search_wiki_articles_for_subchapter, search_qa_pairs_for_subchapter
from src.core.chapter_types import SubChapterInfo,ChapterInfo, BookGenerationContext


class BookGenerator:
    """Generates book content including abstracts, sections, and chapters."""

    def __init__(self, language: str = "ch"):
        self.language = language
        self.config = get_config(language=language)
        self.mcp_url = self.config.mcp_url
        self.wiki_search_api_base = self.config.wiki_search_api_base
        self._prompt_book_module = None

    def _load_prompt_book_module(self):
        if self._prompt_book_module is not None:
            return self._prompt_book_module
        prompt_path = self.config.get_prompt_path("prompt_book.py")
        if not os.path.exists(prompt_path):
            raise FileNotFoundError(f"prompt_book.py not found: {prompt_path}")
        spec = importlib.util.spec_from_file_location("prompt_book", str(prompt_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load prompt module: {prompt_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._prompt_book_module = module
        return module

    async def generate_abstract(self, sub_title: str, topics: List[str], course_name: str,
                              sub_code: str, book_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Generate chapter outline summary."""
        topics_str = ", ".join(topics)

        # 获取Pedia文章
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
        
        prompt_name = self.config.get_prompt_name("abstract", "prompt_abstract")
        prompt_path = self.config.get_prompt_path(prompt_name)
        prompt = self._read_file_safe(prompt_path)
        prompt = prompt.format(
            course_name=course_name,
            subchapter_code=sub_code,
            subchapter_title=sub_title,
            topics=topics_str,
            wiki_content=wiki_content_str,
            book_structure=book_structure
        )

        abstract = await gpt_completion(prompt)
        return {"abstract": abstract, "wiki_content": wiki_content_str}

    async def generate_content(self, ctx: BookGenerationContext, sub_info: SubChapterInfo, sub_code: str, chapter_key: str) -> str:
        """Generate textbook content."""
        sub_title = sub_info.subchapter_title
        topics = sub_info.topics
        topics_str = ", ".join(topics)
        chapter_abstracts = ctx.chapter_abstracts_map.get(chapter_key, {})
        wiki_content = ctx.chapter_wiki_contents_map.get(chapter_key, {}).get(sub_code)

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

        module = self._load_prompt_book_module()
        prompt_config = ctx.prompt_config or {
            "course_type": "理实融合",
            "formal_density": "中",
            "case_strategy": "本学科经典案例",
            "reader_level": "研究生",
            "style_tendency": "问题驱动型",
        }
        config = module.PromptConfig(**prompt_config)
        metadata = {
            "course_name": ctx.course_name,
            "subchapter_code": sub_code,
            "subchapter_title": sub_title,
            "topics": topics_str,
            "wiki_content": wiki_content_str,
            "book_structure": ctx.book_structure_raw,
            "chapter_abstracts": abstracts_str,
        }
        prompt = module.generate_chapter_prompt(config, metadata)

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

    async def insert_project(self, ctx: BookGenerationContext, chapter_info: ChapterInfo, chapter_key: str, subchapter_file_paths: Dict[str, str]) -> tuple:
        """Enhance chapter cohesion and insert projects as线索."""
        chapter_structure = ctx.book_structure_raw.get(chapter_key, {})
        chapter_title = chapter_info.title
        sub_chapters = chapter_info.sub_chapters
        chapter_dir = ctx.get_chapter_dir(chapter_key)
        
        chapter_content_parts = []
        project_qa_text = await self._build_project_qa_text(
            course_name=ctx.course_name,
            chapter_info=chapter_info
        )
        self._save_project_qas(project_qa_text, ctx.output_dir, chapter_dir)
        for sub_code, sub_info in sub_chapters.items():
            sub_title = sub_info.subchapter_title
            input_path = subchapter_file_paths.get(sub_code)
            if os.path.exists(input_path):
                with open(input_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                chapter_content_parts.append(f"## {sub_code} {sub_title}\n{content}")
            else:
                print(f"  [Warning] File not found: {input_path}")

        chapter_content = "\n\n".join(chapter_content_parts)

        prompt_name = self.config.get_prompt_name("book_step2", "prompt_book_step2")
        prompt_path = self.config.get_prompt_path(prompt_name)
        prompt = self._read_file_safe(prompt_path)
        prompt = prompt.format(
            course_name=ctx.course_name,
            chapter_title=chapter_title,
            chapter_structure=chapter_structure,
            chapter_content=chapter_content,
            project_qas=project_qa_text
        )
        new_chapter_content = await gemini_completion(prompt)
        # Check for syntax, format errors, and hallucinations
        prompt_check_name = self.config.get_prompt_name("book_step3", "prompt_book_step3")
        prompt_check_path = self.config.get_prompt_path(prompt_check_name)
        prompt_check = self._read_file_safe(prompt_check_path)
        prompt_check = prompt_check.format(
            course_name=ctx.course_name,
            chapter_title=chapter_title,
            chapter_structure=chapter_structure,
            chapter_content=new_chapter_content,
            project_qas=project_qa_text
        )
        print(f"Starting {chapter_title} chapter content check...")
        check_result = await gpt_completion(prompt_check)
        log_match = re.search(r'<log>\s*(.*?)\s*</log>', check_result, re.DOTALL | re.IGNORECASE)
        content_match = re.search(r'<content>\s*(.*?)\s*</content>', check_result, re.DOTALL | re.IGNORECASE)
        log_text = log_match.group(1).strip() if log_match else ""
        checked_chapter_content = content_match.group(1).strip() if content_match else ""
        print(f"{chapter_title}：Old chapter length {len(chapter_content)}. New chapter length {len(new_chapter_content)}. Checked chapter length: {len(checked_chapter_content)}")

        articles_content = self._decompose_chapter_content(checked_chapter_content)
        return articles_content, checked_chapter_content, log_text

    async def _build_project_qa_text(
        self,
        course_name: str,
        chapter_info: ChapterInfo
    ) -> str:
        """Select one QA per subchapter to form a coherent project chain."""
        chapter_title = chapter_info.title
        sub_chapters = chapter_info.sub_chapters
        raw_cache = self._load_raw_qa_cache(course_name, chapter_title)

        async def _fetch_candidates(sub_code: str, sub_info: SubChapterInfo):
            cached_entry = raw_cache.get(sub_code) if raw_cache else None
            if isinstance(cached_entry, dict) and cached_entry.get("qa_result") is not None:
                print(f"  [Skip] Using existing QA pairs for {sub_code}")
                qa_result = cached_entry.get("qa_result", {}) or {}
                should_update_cache = False
            else:
                try:
                    qa_result = await search_qa_pairs_for_subchapter(
                        subchapter_title=sub_info.subchapter_title,
                        topics=sub_info.topics,
                        max_keywords=10,
                        max_results_per_keyword=1
                    )
                except Exception as e:
                    print(f"  [Warning] QA search failed for {sub_code}: {e}")
                    qa_result = {}
                cached_entry = {
                    "subchapter_title": sub_info.subchapter_title,
                    "topics": sub_info.topics,
                    "qa_result": qa_result
                }
                should_update_cache = True
            qa_pairs = qa_result.get("qa_pairs", [])
            candidates = []
            for idx, qa in enumerate(qa_pairs, 1):
                thumbnail = (qa.get("problem_thumbnail") or "").strip()
                if not thumbnail:
                    continue
                problem_id = (qa.get("problem_id") or qa.get("_id") or "").strip()
                if not problem_id:
                    problem_id = f"{sub_code}-{idx}"
                candidates.append({
                    "problem_id": problem_id,
                    "problem_thumbnail": thumbnail,
                    "problem": (qa.get("problem") or "").strip(),
                    "ground_truth_answer": (qa.get("ground_truth_answer") or "").strip(),
                    "solutions": (qa.get("solutions") or "").strip(),
                })
            payload = None
            if candidates:
                payload = {
                    "title": sub_info.subchapter_title,
                    "candidates": candidates
                }
            return sub_code, payload, cached_entry, should_update_cache

        tasks = [
            _fetch_candidates(sub_code, sub_info)
            for sub_code, sub_info in sub_chapters.items()
        ]
        results = await asyncio.gather(*tasks)
        candidates_by_sub = {}
        cache_updates = {}
        for result in results:
            if not result:
                continue
            sub_code, payload, cached_entry, should_update_cache = result
            if payload:
                candidates_by_sub[sub_code] = payload
            if should_update_cache:
                cache_updates[sub_code] = cached_entry
        if cache_updates:
            merged_cache = dict(raw_cache) if raw_cache else {}
            merged_cache.update(cache_updates)
            self._save_raw_qa_cache(course_name, chapter_title, merged_cache)

        if not candidates_by_sub:
            return ""

        selection = await self._select_project_qas(
            course_name=course_name,
            chapter_title=chapter_title,
            sub_chapters=sub_chapters,
            candidates_by_sub=candidates_by_sub
        )
        if not selection:
            return ""

        lines = ["# 项目线索问答对（每个子章节选一个）"]
        for sub_code, picked in selection.items():
            sub_title = candidates_by_sub.get(sub_code, {}).get("title", "")
            lines.append(f"## {sub_code} {sub_title}")
            lines.append(f"- problem_thumbnail: {picked.get('problem_thumbnail', '')}")
            lines.append(f"- problem: {picked.get('problem', '')}")
            lines.append(f"- ground_truth_answer: {picked.get('ground_truth_answer', '')}")
            lines.append(f"- solutions: {picked.get('solutions', '')}")
        return "\n".join(lines)

    def _get_raw_qa_cache_path(self, course_name: str, chapter_title: str) -> str:
        safe_course = sanitize_filename(course_name)
        safe_chapter = sanitize_filename(chapter_title)
        temp_dir = os.path.join(str(self.config.output_temp_dir), safe_course)
        return os.path.join(temp_dir, f"{safe_chapter}.json")

    def _load_raw_qa_cache(self, course_name: str, chapter_title: str) -> Dict[str, Any]:
        cache_path = self._get_raw_qa_cache_path(course_name, chapter_title)
        if not os.path.exists(cache_path):
            return {}
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as e:
            print(f"  [Warning] Failed to load raw QA cache: {e}")
            return {}

    def _save_raw_qa_cache(self, course_name: str, chapter_title: str, data: Dict[str, Any]) -> None:
        cache_path = self._get_raw_qa_cache_path(course_name, chapter_title)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [Warning] Failed to save raw QA cache: {e}")

    def _save_project_qas(self, project_qa_text: str, output_dir: str, chapter_dir: str) -> None:
        """Save selected project QA pairs to chapter-level file."""
        if not project_qa_text:
            return
        qa_dir = os.path.join(output_dir, "qa_pairs")
        os.makedirs(qa_dir, exist_ok=True)
        qa_path = os.path.join(qa_dir, f"{chapter_dir}.md")
        with open(qa_path, "w", encoding="utf-8") as f:
            f.write(project_qa_text)

    async def _select_project_qas(
        self,
        course_name: str,
        chapter_title: str,
        sub_chapters: Dict[str, Any],
        candidates_by_sub: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, str]]:
        """Use Gemini to pick one QA per subchapter forming a coherent project."""
        prompt_name = self.config.get_prompt_name("select_project_qa", "prompt_select_project_qa")
        prompt_path = self.config.get_prompt_path(prompt_name)
        prompt_template = self._read_file_safe(prompt_path).strip()
        
        # 读取step1章节内容（用于更准确地筛选问答对）
        chapter_abstracts = self._load_chapter_step1_content(course_name, chapter_title)
        
        # 构建候选问答对列表
        candidates_list = []
        for sub_code, info in candidates_by_sub.items():
            title = info.get("title", "")
            candidates = info.get("candidates", [])
            candidates_list.append(f"{sub_code} {title}")
            for idx, cand in enumerate(candidates, 1):
                candidates_list.append(f"  {idx}. [problem_id:{cand.get('problem_id', '')}] {cand.get('problem_thumbnail', '')}")
                candidates_list.append(f"     problem: {cand.get('problem', '')}")
        candidates_str = "\n".join(candidates_list)
        prompt = prompt_template.format(
            course_name=course_name,
            chapter_title=chapter_title,
            sub_chapters=sub_chapters,
            chapter_abstracts=chapter_abstracts,
            candidates=candidates_str
        )
        try:
            response = await gemini_completion(prompt)
        except Exception as e:
            print(f"  [Warning] QA selection failed: {e}")
            response = ""

        selections = {}
        try:
            # 从```json```中解析response，获取selections
            response = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL).group(1)
            data = json.loads(response)
            selections = data.get("selections", {}) if isinstance(data, dict) else {}
        except Exception:
            selections = {}

        if not selections:
            # Fallback: pick the first candidate for each subchapter
            for sub_code, info in candidates_by_sub.items():
                candidates = info.get("candidates", [])
                if candidates:
                    selections[sub_code] = candidates[0].get("problem_id", "")

        # Ensure selections only include known subchapters and valid candidates
        cleaned = {}
        for sub_code, problem_id in selections.items():
            problem_id = problem_id.split(":")[-1].strip()
            info = candidates_by_sub.get(sub_code)
            if not info:
                continue
            candidates = info.get("candidates", [])
            matched = None
            for cand in candidates:
                if cand.get("problem_id") == problem_id:
                    matched = cand
                    break
            if matched:
                cleaned[sub_code] = matched
            elif candidates:
                cleaned[sub_code] = candidates[0]
        return cleaned

    # def _load_chapter_abstracts(self, course_name: str, chapter_title: str) -> Dict[str, str]:
    #     """Load chapter abstracts from file."""
    #     chapter_num = re.search(r'第(\d+)章', chapter_title).group(1)
    #     abstract_base_dir = str(self.config.output_base_dir).replace("books", "abstract")
    #     abstract_path = os.path.join(abstract_base_dir, f"{course_name}/chapter{chapter_num}.md")
    #     if not os.path.exists(abstract_path):
    #         return {}
    #     with open(abstract_path, "r", encoding="utf-8") as f:
    #         abstracts = f.read()
    #         abstracts = re.search(r'<abstract>(.*?)</abstract>', abstracts, re.DOTALL).group(1).strip()
    #     return abstracts

    def _load_chapter_step1_content(self, course_name: str, chapter_title: str) -> str:
        """Load step1 chapter content by concatenating subchapter files."""
        safe_course = sanitize_filename(course_name)
        safe_chapter = sanitize_filename(chapter_title)
        step1_dir = os.path.join(str(self.config.output_base_dir), safe_course, safe_chapter, "step1")

        if not os.path.isdir(step1_dir):
            return ""

        contents = []
        for filename in sorted(os.listdir(step1_dir)):
            if not filename.lower().endswith(".md"):
                continue
            file_path = os.path.join(step1_dir, filename)
            file_content = self._read_file_safe(file_path).strip()
            if not file_content:
                continue
            contents.append(f"### {filename}\n{file_content}")
        return "\n\n".join(contents)
    
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
                    },
                    async_mode=True                                
                )
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
