"""Book generator for creating educational content chapters."""

import os
import re
import json
import asyncio
import importlib.util
from dp.agent.client import MCPClient
from typing import Dict, Any, Optional, List
from src.models import gemini_completion, gpt_completion
from src.utils import get_config, sanitize_filename
from src.core.chapter_types import SubChapterInfo, ChapterInfo, BookGenerationContext
from src.core.material_pack_generator import MaterialPackGenerator


class BookGenerator:
    """Generates book content including abstracts, sections, and chapters."""

    def __init__(self, language: str = "ch"):
        self.language = language
        self.config = get_config(language=language)
        self.mcp_url = self.config.mcp_url
        self._prompt_book_module = None
        self.material_pack_generator = MaterialPackGenerator(language=language)

    def _load_prompt_step2_module(self):
        """加载 prompt_book_step2.py 模块以根据 course_type 获取对应 step2 提示词。"""
        prompt_path = self.config.get_prompt_path("prompt_book_step2.py")
        if not os.path.exists(prompt_path):
            raise FileNotFoundError(f"prompt_book_step2.py not found: {prompt_path}")
        spec = importlib.util.spec_from_file_location("prompt_book_step2", str(prompt_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load module: {prompt_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

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

    async def generate_content(self, ctx: BookGenerationContext, sub_info: SubChapterInfo, sub_code: str, chapter_key: str) -> str:
        """Generate textbook content using material-pack context."""
        sub_title = sub_info.subchapter_title
        topics = sub_info.topics
        topics_str = ", ".join(topics)
        chapter_abstracts = (ctx.chapter_abstracts_map or {}).get(chapter_key, {})
        wiki_content = self._load_wiki_content_from_pack(ctx, chapter_key, sub_code, sub_title)
        if not chapter_abstracts:
            chapter_abstracts, wiki_contents = self._load_chapter_abstracts_from_material_pack(ctx, chapter_key)
            if chapter_abstracts:
                if ctx.chapter_abstracts_map is None:
                    ctx.chapter_abstracts_map = {}
                ctx.chapter_abstracts_map[chapter_key] = chapter_abstracts
            if wiki_contents and not wiki_content:
                wiki_content = wiki_contents.get(sub_code)

        if wiki_content is None:
            print(f"  [Warning] Missing wiki content in material pack for {sub_code}.")
            wiki_content_str = ""
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
        
        chapter_content_parts = []
        project_qa_text = await self._build_project_qa_text(
            ctx=ctx,
            chapter_info=chapter_info,
            chapter_key=chapter_key,
        )
        self._save_project_qas(ctx, chapter_key, project_qa_text)
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

        # 根据课程类型选择 step2 提示词：理论主导 → 章节末练习题；其余 → 实战项目（prompt_book_step2）
        course_type = None
        if ctx.prompt_config:
            course_type = ctx.prompt_config.get("course_type")
        if course_type is not None:
            step2_module = self._load_prompt_step2_module()
            prompt = step2_module.get_step2_prompt(course_type, self.config.prompts_base_dir)
        else:
            prompt_name = self.config.get_prompt_name("book_step2", "prompt_book_step2")
            prompt_path = self._resolve_prompt_path(ctx, prompt_name)
            prompt = self._read_file_safe(prompt_path)
        prompt = prompt.format(
            course_name=ctx.course_name,
            chapter_title=chapter_title,
            chapter_structure=chapter_structure,
            chapter_content=chapter_content,
            project_qas=project_qa_text
        )
        new_chapter_content = await gemini_completion(prompt)
        # 第一步结果按节切分，再对每节分别纠错，避免整章合并纠错时内容过长
        first_line = ""
        if new_chapter_content and new_chapter_content.strip():
            first_line = new_chapter_content.strip().split("\n")[0]
        articles_after_step1 = self._decompose_chapter_content(new_chapter_content)
        if not articles_after_step1:
            articles_content = {}
            return articles_content, new_chapter_content, ""

        print(f"Start checking {chapter_title}")
        prompt_check_name = self.config.get_prompt_name("book_step3", "prompt_book_step3")
        prompt_check_path = self._resolve_prompt_path(ctx, prompt_check_name)
        prompt_check_template = self._read_file_safe(prompt_check_path)
        section_titles = list(articles_after_step1.keys())
        checked_sections = []
        log_parts = []
        for i, (section_title, section_content) in enumerate[tuple[str, str]](articles_after_step1.items(), 1):
            print(f"  [{chapter_title}] 纠错 {i}/{len(section_titles)}: {section_title[:40]}...")
            prompt_check = prompt_check_template.format(
                course_name=ctx.course_name,
                chapter_title=chapter_title,
                chapter_structure=chapter_structure,
                chapter_content=section_content,
                project_qas=project_qa_text
            )
            check_result = await gpt_completion(prompt_check)
            log_match = re.search(r'<log>\s*(.*?)\s*</log>', check_result, re.DOTALL | re.IGNORECASE)
            content_match = re.search(r'<content>\s*(.*?)\s*</content>', check_result, re.DOTALL | re.IGNORECASE)
            log_parts.append(log_match.group(1).strip() if log_match else "")
            checked_sections.append(content_match.group(1).strip() if content_match else section_content)
        log_text = "\n\n".join(p for p in log_parts if p)
        checked_chapter_content = ("\n\n".join(checked_sections))
        if first_line:
            checked_chapter_content = first_line + "\n\n" + checked_chapter_content
        print(f"{chapter_title}：Step1 长度 {len(new_chapter_content)}，纠错后全长 {len(checked_chapter_content)}")
        articles_content = self._decompose_chapter_content(checked_chapter_content)
        return articles_content, checked_chapter_content, log_text

    async def _build_project_qa_text(
        self,
        ctx: BookGenerationContext,
        chapter_info: ChapterInfo,
        chapter_key: str,
    ) -> str:
        """Select one QA per subchapter to form a coherent project chain."""
        chapter_title = chapter_info.title
        sub_chapters = chapter_info.sub_chapters
        raw_cache = self._load_raw_qa_cache(ctx, chapter_key)

        async def _fetch_candidates(sub_code: str, sub_info: SubChapterInfo):
            cached_entry = raw_cache.get(sub_code) if raw_cache else None
            if isinstance(cached_entry, dict) and cached_entry.get("qa_result") is not None:
                print(f"  [Skip] Using existing QA pairs for {sub_code}")
                qa_result = cached_entry.get("qa_result", {}) or {}
            else:
                print(f"  [Warning] Material pack QA missing for {sub_code}, skip.")
                qa_result = {}
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
            return sub_code, payload

        tasks = [
            _fetch_candidates(sub_code, sub_info)
            for sub_code, sub_info in sub_chapters.items()
        ]
        results = await asyncio.gather(*tasks)
        candidates_by_sub = {}
        for result in results:
            if not result:
                continue
            sub_code, payload = result
            if payload:
                candidates_by_sub[sub_code] = payload

        if not candidates_by_sub:
            return ""

        selection = await self._select_project_qas(
            ctx=ctx,
            chapter_key=chapter_key,
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

    def _get_raw_qa_cache_path(self, ctx: BookGenerationContext, chapter_key: str) -> str:
        """Raw QA cache JSON path in material pack."""
        chapter_dir = ctx.get_chapter_dir(chapter_key)
        material_pack_dir = self._get_material_pack_dir(ctx)
        return os.path.join(material_pack_dir, "qa_pairs", f"{chapter_dir}.json")

    def _load_raw_qa_cache(self, ctx: BookGenerationContext, chapter_key: str) -> Dict[str, Any]:
        cache_path = self._get_raw_qa_cache_path(ctx, chapter_key)
        if not os.path.exists(cache_path):
            return {}
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as e:
            print(f"  [Warning] Failed to load raw QA cache: {e}")
            return {}

    def _save_project_qas(self, ctx: BookGenerationContext, chapter_key: str, project_qa_text: str) -> None:
        """Save selected project QA pairs (filtered) to {course}/temp/qa_pairs/<chapter_dir>.md."""
        if not project_qa_text:
            return
        chapter_dir = ctx.get_chapter_dir(chapter_key)
        os.makedirs(ctx.temp_qa_pairs_dir, exist_ok=True)
        qa_path = os.path.join(ctx.temp_qa_pairs_dir, f"{chapter_dir}.md")
        with open(qa_path, "w", encoding="utf-8") as f:
            f.write(project_qa_text)

    async def _select_project_qas(
        self,
        ctx: BookGenerationContext,
        chapter_key: str,
        chapter_title: str,
        sub_chapters: Dict[str, Any],
        candidates_by_sub: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, str]]:
        """Use Gemini to pick one QA per subchapter forming a coherent project."""
        prompt_name = self.config.get_prompt_name("select_project_qa", "prompt_select_project_qa")
        prompt_path = self._resolve_prompt_path(ctx, prompt_name)
        prompt_template = self._read_file_safe(prompt_path).strip()
        
        # 读取step1章节内容（用于更准确地筛选问答对）
        chapter_abstracts = self._load_chapter_step1_content(ctx, chapter_key)
        
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
            course_name=ctx.course_name,
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

    def _load_chapter_abstracts_from_material_pack(self, ctx: BookGenerationContext, chapter_key: str) -> tuple[Dict[str, str], Dict[str, str]]:
        chapter_dir = ctx.get_chapter_dir(chapter_key)
        material_pack_dir = self._get_material_pack_dir(ctx)
        abstract_path = os.path.join(material_pack_dir, "abstracts", f"{chapter_dir}.md")
        if not os.path.exists(abstract_path):
            return {}, {}
        content = self._read_file_safe(abstract_path)
        abstracts: Dict[str, str] = {}
        wiki_contents: Dict[str, str] = {}

        abstract_match = re.search(r"<abstract>(.*?)</abstract>", content, re.DOTALL)
        abstract_block = abstract_match.group(1).strip() if abstract_match else ""
        if abstract_block:
            parts = re.split(r"###\s*子章节\s+", abstract_block)
            for part in parts[1:]:
                lines = part.strip().splitlines()
                if not lines:
                    continue
                header_line = lines[0]
                if "：" in header_line:
                    sub_code = header_line.split("：", 1)[0].strip()
                elif ":" in header_line:
                    sub_code = header_line.split(":", 1)[0].strip()
                else:
                    continue
                abstracts[sub_code] = "\n".join(lines[1:]).strip()

        for match in re.finditer(r"<wiki_content([0-9.]+)>(.*?)</wiki_content\1>", content, re.DOTALL):
            wiki_contents[match.group(1)] = match.group(2).strip()
        return abstracts, wiki_contents

    def _load_wiki_content_from_pack(
        self,
        ctx: BookGenerationContext,
        chapter_key: str,
        sub_code: str,
        sub_title: str,
    ) -> str:
        chapter_dir = ctx.get_chapter_dir(chapter_key)
        sub_folder = f"{sub_code.replace('.', '_')}_{sanitize_filename(sub_title, 40)}"
        wiki_dir = os.path.join(self._get_material_pack_dir(ctx), "wiki_articles", chapter_dir, sub_folder)
        if not os.path.isdir(wiki_dir):
            return ""
        contents = []
        for filename in sorted(os.listdir(wiki_dir)):
            if not filename.lower().endswith(".md"):
                continue
            file_path = os.path.join(wiki_dir, filename)
            text = self._read_file_safe(file_path).strip()
            if text:
                contents.append(text)
        return "\n\n".join(contents)

    def _get_material_pack_dir(self, ctx: BookGenerationContext) -> str:
        return ctx.material_pack_dir or self.material_pack_generator.get_material_pack_dir(
            ctx.course_name,
            ctx.course_dir,
        )

    def _resolve_prompt_path(self, ctx: BookGenerationContext, prompt_name: str) -> str:
        pack_prompt_path = os.path.join(self._get_material_pack_dir(ctx), "prompts", prompt_name)
        if os.path.exists(pack_prompt_path):
            return pack_prompt_path
        return str(self.config.get_prompt_path(prompt_name))

    def _load_chapter_step1_content(self, ctx: BookGenerationContext, chapter_key: str) -> str:
        """Load step1 chapter content by concatenating subchapter files (new layout)."""
        step1_dir = ctx.get_chapter_step1_dir(chapter_key)

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
            async with MCPClient(self.mcp_url) as client:
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
