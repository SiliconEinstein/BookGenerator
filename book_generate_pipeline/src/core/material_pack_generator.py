"""Material pack generation for textbook pipeline."""

import os
import re
import json
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.models import gpt_completion
from src.utils import get_config, sanitize_filename
from src.tools import search_qa_pairs_for_subchapter, search_wiki_articles_for_subchapter
from src.tools.draw_image.draw_image_agent import DrawImageAgent
from src.core.chapter_types import BookGenerationContext


class MaterialPackGenerator:
    """Generate and load reusable material packs before content writing."""

    COURSE_INFO_FIELD_MAP = {
        "course_name": "教材名称",
        "language": "语言",
        "target_audience": "面向人群",
        "teaching_methodology": "教学方式",
        "teaching_objectives": "教学目的",
        "teaching_requirements": "教学要求",
        "style_tendency": "教材行文风格",
    }
    EXCLUDED_PROMPT_PREFIXES = ("prompt_chapter",)

    def __init__(self, language: str = "ch"):
        self.language = language
        self.config = get_config(language=language)
        self.abstract_semaphore = asyncio.Semaphore(20)
        self.practical_case_semaphore = asyncio.Semaphore(8)
        self._draw_agent = DrawImageAgent()

    def get_material_pack_dir(self, course_name: str, course_dir: Optional[str] = None) -> str:
        if course_dir:
            return os.path.join(course_dir, "pack")
        safe_course_name = sanitize_filename(course_name, max_len=60)
        return os.path.join("output", safe_course_name, "pack")

    def _get_pack_subdir(self, pack_dir: str, subdir: str) -> str:
        path = os.path.join(pack_dir, subdir)
        os.makedirs(path, exist_ok=True)
        return path

    async def generate_material_pack(
        self,
        ctx: BookGenerationContext,
        chapter_path: str,
        preface_inputs: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Build a complete material pack and return in-memory maps."""
        pack_dir = self.get_material_pack_dir(ctx.course_name, ctx.course_dir)
        os.makedirs(pack_dir, exist_ok=True)
        book_info = self._load_book_info(ctx)
        self._warn_missing_book_info_fields(book_info)
        self._write_pack_readme(pack_dir, ctx.course_name)
        built_count, skipped_count = self._build_course_prompts(pack_dir, ctx, book_info)
        if skipped_count:
            print(f"[Prompts] 已存在文件跳过：{skipped_count} 个。")
        if built_count:
            print(f"[Prompts] 新增生成：{built_count} 个。")
            self._confirm_prompt_modification(pack_dir)
        else:
            print("[Prompts] 无需新增，沿用现有 prompts。")

        syllabus_text = self._read_file_safe(chapter_path)
        self._save_book_info_files(pack_dir, ctx, syllabus_text, book_info)
        preface_path = os.path.join(pack_dir, "book_info", "preface.md")
        if os.path.exists(preface_path):
            regenerate_preface = self._ask_yes_no(
                f"[Preface] 检测到已存在前言：{preface_path}\n是否重新生成前言？(yes/no)："
            )
            if regenerate_preface:
                await self._generate_preface(
                    pack_dir, ctx, syllabus_text, preface_inputs or {}, book_info, force=True
                )
            else:
                print("[Preface] 跳过前言生成。")
        else:
            await self._generate_preface(pack_dir, ctx, syllabus_text, preface_inputs or {}, book_info)

        abstract_dir = os.path.join(pack_dir, "abstracts")
        if self._dir_has_files(abstract_dir):
            regenerate_abstracts = self._ask_yes_no(
                f"[Abstracts] 检测到已存在摘要目录：{abstract_dir}\n是否重新生成摘要与 wiki 文章？(yes/no)："
            )
            if regenerate_abstracts:
                self._clear_dir(abstract_dir)
                self._clear_dir(os.path.join(pack_dir, "wiki_articles"))
                chapter_abstracts_map, chapter_wiki_contents_map = await self._generate_abstracts(pack_dir, ctx)
            else:
                print("[Abstracts] 跳过摘要重新生成，使用现有文件。")
                chapter_abstracts_map, chapter_wiki_contents_map = self._load_abstract_maps_from_pack(pack_dir, ctx)
        else:
            chapter_abstracts_map, chapter_wiki_contents_map = await self._generate_abstracts(pack_dir, ctx)

        summary_images_dir = os.path.join(pack_dir, "summary_images")
        if self._dir_has_files(summary_images_dir):
            regenerate_summary_images = self._ask_yes_no(
                f"[Summary Images] 检测到已存在章节摘要插图目录：{summary_images_dir}\n是否重新生成摘要插图？(yes/no)："
            )
            if regenerate_summary_images:
                self._clear_dir(summary_images_dir)
                await self._generate_summary_images(pack_dir, ctx, chapter_abstracts_map)
            else:
                print("[Summary Images] 跳过摘要插图生成。")
        else:
            await self._generate_summary_images(pack_dir, ctx, chapter_abstracts_map)

        qa_pairs_dir = os.path.join(pack_dir, "qa_pairs")
        if self._dir_has_files(qa_pairs_dir):
            regenerate_qa_pairs = self._ask_yes_no(
                f"[QA Pairs] 检测到已存在问答对目录：{qa_pairs_dir}\n是否重新生成问答对？(yes/no)："
            )
            if regenerate_qa_pairs:
                self._clear_dir(qa_pairs_dir)
                chapter_qa_pairs_map = await self._generate_qa_pairs(pack_dir, ctx)
            else:
                print("[QA Pairs] 跳过问答对重新生成，使用现有文件。")
                chapter_qa_pairs_map = self._load_qa_pairs_from_pack(pack_dir, ctx)
        else:
            generate_qa_pairs = self._ask_yes_no(
                f"[QA Pairs] 请问是否需要检索问答对？(yes/no)："
            )
            if generate_qa_pairs:
                chapter_qa_pairs_map = await self._generate_qa_pairs(pack_dir, ctx)
            else:
                print("[QA Pairs] 跳过问答对检索。")
                chapter_qa_pairs_map = self._load_qa_pairs_from_pack(pack_dir, ctx)

        practical_case_dir = os.path.join(pack_dir, "notebooks")
        generate_practical_cases = self._ask_yes_no(
            f"[Practical Cases] 请问是否需要生成实战案例 notebook？(yes/no)："
        )
        if generate_practical_cases:
            if self._dir_has_files(practical_case_dir):
                print(
                    "[Practical Cases] 检测到已存在实战案例目录，采用不覆盖策略："
                    "已存在 notebook 跳过，仅补齐缺失文件。"
                )
                practical_case_paths = await self._generate_practical_case_notebooks(pack_dir, ctx)
            else:
                practical_case_paths = await self._generate_practical_case_notebooks(pack_dir, ctx)
        else:
            print("[Practical Cases] 跳过实战案例 notebook 生成。")
            practical_case_paths = self._list_practical_case_notebooks(pack_dir)

        return {
            "material_pack_dir": pack_dir,
            "chapter_abstracts_map": chapter_abstracts_map,
            "chapter_wiki_contents_map": chapter_wiki_contents_map,
            "chapter_qa_pairs_map": chapter_qa_pairs_map,
            "practical_case_paths": practical_case_paths,
        }

    def load_material_pack(self, ctx: BookGenerationContext) -> Dict[str, Any]:
        """Load existing material pack context without regenerating."""
        pack_dir = self.get_material_pack_dir(ctx.course_name, ctx.course_dir)
        abstract_dir = os.path.join(pack_dir, "abstracts")
        chapter_abstracts_map: Dict[str, Dict[str, str]] = {}
        chapter_wiki_contents_map: Dict[str, Dict[str, str]] = {}
        if not os.path.isdir(abstract_dir):
            return {
                "material_pack_dir": pack_dir,
                "chapter_abstracts_map": chapter_abstracts_map,
                "chapter_wiki_contents_map": chapter_wiki_contents_map,
            }
        for chapter_key in ctx.sorted_chapters:
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            abstract_path = os.path.join(abstract_dir, f"{chapter_dir}.md")
            if not os.path.exists(abstract_path):
                continue
            abstracts, wiki_contents = self._load_abstract_file(abstract_path)
            chapter_abstracts_map[chapter_key] = abstracts
            chapter_wiki_contents_map[chapter_key] = wiki_contents
        return {
            "material_pack_dir": pack_dir,
            "chapter_abstracts_map": chapter_abstracts_map,
            "chapter_wiki_contents_map": chapter_wiki_contents_map,
        }

    def _save_book_info_files(
        self, pack_dir: str, ctx: BookGenerationContext, chapter_file_content: str, book_info: Dict[str, str]
    ) -> None:
        info_dir = self._get_pack_subdir(pack_dir, "book_info")
        syllabus_match = re.search(r"<syllabus>(.*?)</syllabus>", chapter_file_content, re.DOTALL)
        syllabus_content = syllabus_match.group(1).strip() if syllabus_match else chapter_file_content.strip()
        with open(os.path.join(info_dir, "syllabus.md"), "w", encoding="utf-8") as f:
            f.write(syllabus_content)
        with open(os.path.join(info_dir, "book_info.json"), "w", encoding="utf-8") as f:
            json.dump(book_info, f, ensure_ascii=False, indent=2)
        practical_case_src = os.path.join(ctx.book_info_dir, "practical_case.json")
        practical_case_dst = os.path.join(info_dir, "practical_case.json")
        if os.path.exists(practical_case_src):
            shutil.copy2(practical_case_src, practical_case_dst)

    async def _generate_preface(
        self,
        pack_dir: str,
        ctx: BookGenerationContext,
        syllabus_text: str,
        preface_inputs: Dict[str, str],
        book_info: Dict[str, str],
        force: bool = False,
    ) -> None:
        info_dir = self._get_pack_subdir(pack_dir, "book_info")
        preface_path = os.path.join(info_dir, "preface.md")
        if os.path.exists(preface_path) and not force:
            return

        syllabus_match = re.search(r"<syllabus>(.*?)</syllabus>", syllabus_text, re.DOTALL)
        outline_text = syllabus_match.group(1).strip() if syllabus_match else syllabus_text.strip()
        prompt_template = self._load_prompt_template(pack_dir, "prompt_preface")
        if not prompt_template.strip():
            prompt_template = (
                "请基于以下信息撰写《{course_name}》教材前言：\n"
                "- 课程名称：{course_name}\n"
                "- 授课对象：{target_audience}\n"
                "- 教学目的：{teaching_objectives}\n"
                "- 教学要求：{teaching_requirements}\n"
                "- 教学方式：{teaching_methodology}\n"
                "教材大纲：\n{syllabus}\n"
                "要求：语言正式、结构完整、便于教师理解教材设计意图。"
            )

        prompt = prompt_template.format(
            course_name=ctx.course_name,
            target_audience=preface_inputs.get("target_audience", book_info.get("面向人群", "{{授课对象}}")),
            teaching_objectives=preface_inputs.get("teaching_objectives", book_info.get("教学目的", "{{教学目的}}")),
            teaching_requirements=preface_inputs.get("teaching_requirements", book_info.get("教学要求", "{{教学要求}}")),
            teaching_methodology=preface_inputs.get("teaching_methodology", book_info.get("教学方式", "{{教学方式}}")),
            syllabus=outline_text,
        )
        preface = await gpt_completion(prompt)
        with open(preface_path, "w", encoding="utf-8") as f:
            f.write(preface.strip())

    async def _generate_abstracts(
        self, pack_dir: str, ctx: BookGenerationContext
    ) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
        abstract_dir = self._get_pack_subdir(pack_dir, "abstracts")
        chapter_abstracts_map: Dict[str, Dict[str, str]] = {}
        chapter_wiki_contents_map: Dict[str, Dict[str, str]] = {}

        for chapter_key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(chapter_key):
                continue
            chapter_info = ctx.book_structure[chapter_key]
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            abstract_path = os.path.join(abstract_dir, f"{chapter_dir}.md")
            if os.path.exists(abstract_path):
                abstracts, wiki_contents = self._load_abstract_file(abstract_path)
                chapter_abstracts_map[chapter_key] = abstracts
                chapter_wiki_contents_map[chapter_key] = wiki_contents
                continue

            tasks = []
            for sub_code, sub_info in chapter_info.sub_chapters.items():
                if ctx.should_process_subchapter(sub_code):
                    tasks.append(self._generate_single_abstract(pack_dir, ctx, chapter_key, sub_code, sub_info))
            results = await asyncio.gather(*tasks) if tasks else []
            abstracts = {sub_code: abst for _, sub_code, abst, _ in results}
            wiki_contents = {sub_code: wiki for _, sub_code, _, wiki in results}

            with open(abstract_path, "w", encoding="utf-8") as f:
                total_abstracts = ""
                for sub_code, abst in abstracts.items():
                    sub_title = chapter_info.sub_chapters[sub_code].subchapter_title
                    total_abstracts += f"### 子章节 {sub_code}：{sub_title}\n{abst}\n\n"
                f.write(f"<abstract>{total_abstracts}</abstract>\n\n")

            chapter_abstracts_map[chapter_key] = abstracts
            chapter_wiki_contents_map[chapter_key] = wiki_contents

        return chapter_abstracts_map, chapter_wiki_contents_map

    async def _generate_single_abstract(
        self, pack_dir: str, ctx: BookGenerationContext, chapter_key: str, sub_code: str, sub_info: Any
    ) -> Tuple[str, str, str, str]:
        async with self.abstract_semaphore:
            try:
                result = await self._generate_abstract_for_subchapter(
                    pack_dir=pack_dir,
                    chapter_dir=ctx.get_chapter_dir(chapter_key),
                    sub_title=sub_info.subchapter_title,
                    topics=sub_info.topics,
                    course_name=ctx.course_name,
                    sub_code=sub_code,
                    book_structure=ctx.book_structure_raw,
                )
                return chapter_key, sub_code, result.get("abstract", ""), result.get("wiki_content", "")
            except Exception as e:
                print(f"  [Warning] Failed to generate abstract for {sub_code}: {e}")
                return chapter_key, sub_code, "[摘要生成失败]", ""

    async def _generate_abstract_for_subchapter(
        self,
        pack_dir: str,
        chapter_dir: str,
        sub_title: str,
        topics: List[str],
        course_name: str,
        sub_code: str,
        book_structure: Dict[str, Any],
    ) -> Dict[str, str]:
        topics_str = ", ".join(topics)
        wiki_articles_content, wiki_titles = await search_wiki_articles_for_subchapter(
            subchapter_title=sub_title,
            topics=topics,
            k=5,
            language="zh-CN" if self.language == "ch" else "en-US",
        )
        wiki_content_str = "\n\n".join(wiki_articles_content) if wiki_articles_content else "No related wiki articles found."
        self._save_wiki_articles(
            pack_dir=pack_dir,
            chapter_dir=chapter_dir,
            sub_code=sub_code,
            sub_title=sub_title,
            wiki_articles_content=wiki_articles_content,
            wiki_titles=wiki_titles,
        )

        prompt = self._load_prompt_template(pack_dir, self.config.get_prompt_name("abstract", "prompt_abstract"))
        prompt = prompt.format(
            course_name=course_name,
            subchapter_code=sub_code,
            subchapter_title=sub_title,
            topics=topics_str,
            wiki_content=wiki_content_str,
            book_structure=book_structure,
        )
        abstract = await gpt_completion(prompt)
        return {"abstract": abstract, "wiki_content": wiki_content_str}

    def _save_wiki_articles(
        self,
        pack_dir: str,
        chapter_dir: str,
        sub_code: str,
        sub_title: str,
        wiki_articles_content: List[str],
        wiki_titles: Optional[List[str]] = None,
    ) -> None:
        wiki_root = self._get_pack_subdir(pack_dir, "wiki_articles")
        chapter_folder = self._get_pack_subdir(wiki_root, chapter_dir)
        sub_folder_name = f"{sub_code.replace('.', '_')}_{sanitize_filename(sub_title, 40)}"
        sub_folder = self._get_pack_subdir(chapter_folder, sub_folder_name)

        index_items = []
        used_names = set()
        for idx, content in enumerate(wiki_articles_content):
            raw_title = ""
            if wiki_titles and idx < len(wiki_titles):
                raw_title = str(wiki_titles[idx] or "").strip()
            if not raw_title:
                raw_title = self._extract_title_from_wiki_content(content)
            if not raw_title:
                raw_title = f"article_{idx:02d}"

            safe_title = sanitize_filename(raw_title, max_len=80) or f"article_{idx:02d}"
            file_name = f"{safe_title}.md"
            if file_name in used_names:
                file_name = f"{safe_title}_{idx:02d}.md"
            used_names.add(file_name)

            file_path = os.path.join(sub_folder, file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content or "")
            index_items.append({"index": idx, "title": raw_title, "file": file_name})

        with open(os.path.join(sub_folder, "index.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "subchapter_code": sub_code,
                    "subchapter_title": sub_title,
                    "count": len(index_items),
                    "items": index_items,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    async def _generate_summary_images(
        self,
        pack_dir: str,
        ctx: BookGenerationContext,
        chapter_abstracts_map: Dict[str, Dict[str, str]],
    ) -> None:
        images_dir = self._get_pack_subdir(pack_dir, "summary_images")
        prompt_dir = str(Path(__file__).resolve().parents[1] / "tools" / "draw_image" / "prompt")

        for chapter_key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(chapter_key):
                continue
            chapter_info = ctx.book_structure[chapter_key]
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            chapter_image_dir = self._get_pack_subdir(images_dir, chapter_dir)
            image_path = os.path.join(chapter_image_dir, "image_0.png")
            if os.path.exists(image_path):
                continue

            abstracts = chapter_abstracts_map.get(chapter_key, {})
            abstract_text = "\n\n".join(
                f"子章节 {code}: {text}" for code, text in abstracts.items() if text.strip()
            )
            context = (
                f"课程：{ctx.course_name}\n"
                f"章节：{chapter_info.title}\n"
                "以下是本章子章节摘要，请生成用于教师快速把握本章知识结构的概念插图：\n"
                f"{abstract_text}"
            )
            generated_path = await self._draw_agent.draw_by_text(
                context=context,
                output_dir=chapter_image_dir,
                image_name="summary.png",
                reason="该图用于素材包阶段，帮助教师快速理解本章知识脉络与内容组织方式。",
                prompt_dir=prompt_dir,
            )
            manifest = {
                "chapter_key": chapter_key,
                "chapter_title": chapter_info.title,
                "source": "chapter_abstracts",
                "image_path": generated_path or image_path,
            }
            with open(os.path.join(chapter_image_dir, "images.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

    async def _generate_qa_pairs(self, pack_dir: str, ctx: BookGenerationContext) -> Dict[str, Dict[str, Any]]:
        qa_dir = self._get_pack_subdir(pack_dir, "qa_pairs")
        chapter_qa_pairs_map: Dict[str, Dict[str, Any]] = {}

        for chapter_key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(chapter_key):
                continue
            chapter_info = ctx.book_structure[chapter_key]
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            qa_path = os.path.join(qa_dir, f"{chapter_dir}.json")
            if os.path.exists(qa_path):
                continue

            chapter_cache: Dict[str, Any] = {}
            for sub_code, sub_info in chapter_info.sub_chapters.items():
                if not ctx.should_process_subchapter(sub_code):
                    continue
                try:
                    qa_result = await search_qa_pairs_for_subchapter(
                        subchapter_title=sub_info.subchapter_title,
                        topics=sub_info.topics,
                        max_keywords=10,
                        max_results_per_keyword=1,
                    )
                except Exception as e:
                    print(f"  [Warning] QA search failed for {sub_code}: {e}")
                    qa_result = {"qa_pairs": [], "keywords": [], "search_results": [], "summary": {}}

                qa_pairs = qa_result.get("qa_pairs", [])
                if qa_pairs:
                    await self._translate_problem_thumbnails(qa_pairs)

                chapter_cache[sub_code] = {
                    "subchapter_title": sub_info.subchapter_title,
                    "topics": sub_info.topics,
                    "qa_result": qa_result,
                }

            with open(qa_path, "w", encoding="utf-8") as f:
                json.dump(chapter_cache, f, ensure_ascii=False, indent=2)
            chapter_qa_pairs_map[chapter_key] = chapter_cache

        return chapter_qa_pairs_map

    async def _translate_problem_thumbnails(self, qa_pairs: List[Dict[str, Any]]) -> None:
        originals = []
        for qa in qa_pairs:
            text = (qa.get("problem_thumbnail") or "").strip()
            if text and not self._contains_chinese(text):
                originals.append(text)
        originals = list(dict.fromkeys(originals))
        if not originals:
            return

        prompt = (
            "请将下列题目标题翻译为中文，保持学术准确、简洁，不要添加解释。\n"
            "只返回 JSON，格式：{\"translations\":[{\"source\":\"原文\",\"translated\":\"中文\"}]}\n"
            f"原文列表：{json.dumps(originals, ensure_ascii=False)}"
        )
        response = await gpt_completion(prompt)
        mapping: Dict[str, str] = {}
        try:
            json_text = response.strip()
            block_match = re.search(r"```json\s*(.*?)\s*```", json_text, re.DOTALL | re.IGNORECASE)
            if block_match:
                json_text = block_match.group(1).strip()
            payload = json.loads(json_text)
            for item in payload.get("translations", []):
                source = (item.get("source") or "").strip()
                translated = (item.get("translated") or "").strip()
                if source and translated:
                    mapping[source] = translated
        except Exception:
            mapping = {}

        if not mapping:
            return
        for qa in qa_pairs:
            source = (qa.get("problem_thumbnail") or "").strip()
            if source in mapping:
                qa["problem_thumbnail"] = mapping[source]

    @staticmethod
    def _contains_chinese(text: str) -> bool:
        return re.search(r"[\u4e00-\u9fff]", text) is not None

    def _load_abstract_file(self, abstract_path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        content = self._read_file_safe(abstract_path)
        abstracts: Dict[str, str] = {}
        wiki_contents: Dict[str, str] = {}

        abstract_block = None
        abstract_match = re.search(r"<abstract>(.*?)</abstract>", content, re.DOTALL)
        if abstract_match:
            abstract_block = abstract_match.group(1).strip()

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

    def _load_prompt_template(self, pack_dir: str, prompt_name: str) -> str:
        pack_prompt_path = os.path.join(pack_dir, "prompts", prompt_name)
        if os.path.exists(pack_prompt_path):
            return self._read_file_safe(pack_prompt_path)
        prompt_path = self.config.get_prompt_path(prompt_name)
        return self._read_file_safe(str(prompt_path))

    def _load_book_info(self, ctx: BookGenerationContext) -> Dict[str, str]:
        info_path = os.path.join(ctx.book_info_dir, "book_info.json")
        if not os.path.exists(info_path):
            return {}
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _build_course_prompts(
        self, pack_dir: str, ctx: BookGenerationContext, course_info: Dict[str, str]
    ) -> Tuple[int, int]:
        prompts_dir = self._get_pack_subdir(pack_dir, "prompts")
        templates_dir = self.config.prompts_base_dir
        built_count = 0
        skipped_count = 0
        replacements = {
            "course_name": course_info.get("教材名称", ctx.course_name),
            "language": course_info.get("语言", "中文" if self.language == "ch" else "英文"),
            "target_audience": course_info.get("面向人群", "{{面向人群}}"),
            "teaching_methodology": course_info.get("教学方式", "{{教学方式}}"),
            "teaching_objectives": course_info.get("教学目的", "{{教学目的}}"),
            "teaching_requirements": course_info.get("教学要求", "{{教学要求}}"),
            "style_tendency": course_info.get("教材行文风格", "{{教材行文风格}}"),
            "教材名称": course_info.get("教材名称", ctx.course_name),
            "语言": course_info.get("语言", "中文" if self.language == "ch" else "英文"),
            "面向人群": course_info.get("面向人群", "{{面向人群}}"),
            "教学方式": course_info.get("教学方式", "{{教学方式}}"),
            "教学目的": course_info.get("教学目的", "{{教学目的}}"),
            "教学要求": course_info.get("教学要求", "{{教学要求}}"),
            "教材行文风格": course_info.get("教材行文风格", "{{教材行文风格}}"),
        }
        for filename in os.listdir(templates_dir):
            src_path = os.path.join(templates_dir, filename)
            if not os.path.isfile(src_path):
                continue
            if filename.endswith(".py"):
                continue
            if self._is_chapter_generation_prompt(filename):
                continue
            content = self._read_file_safe(src_path)
            content = content.replace("{education_level}", "{target_audience}")
            rendered = self._partial_fill_template(content, replacements)
            dst_path = os.path.join(prompts_dir, filename)
            if os.path.exists(dst_path):
                skipped_count += 1
                continue
            with open(dst_path, "w", encoding="utf-8") as f:
                f.write(rendered)
            built_count += 1
        # 为绘图流程补齐 draw_by_text（不覆盖），用于 draw_images.py 优先读取 pack 提示词。
        draw_prompt_src = (
            Path(__file__).resolve().parents[1] / "tools" / "draw_image" / "prompt" / "draw_by_text"
        )
        draw_prompt_dst = os.path.join(prompts_dir, "draw_by_text")
        if os.path.isfile(draw_prompt_src):
            if os.path.exists(draw_prompt_dst):
                skipped_count += 1
            else:
                draw_prompt_content = self._read_file_safe(str(draw_prompt_src))
                with open(draw_prompt_dst, "w", encoding="utf-8") as f:
                    f.write(draw_prompt_content)
                built_count += 1
        return built_count, skipped_count

    def _is_chapter_generation_prompt(self, filename: str) -> bool:
        return any(filename.startswith(prefix) for prefix in self.EXCLUDED_PROMPT_PREFIXES)

    def _confirm_prompt_modification(self, pack_dir: str) -> None:
        prompts_dir = os.path.join(pack_dir, "prompts")
        print(
            f"[Prompt Check] 已生成初版 prompts：{prompts_dir}\n"
            "是否需要先手动修改 prompts？请输入 yes 或 no："
        )
        while True:
            choice = input("> ").strip().lower()
            if choice in {"yes", "y"}:
                print("[Stopped] 已按要求终止，请先修改 prompts 后再重新运行。")
                raise SystemExit(0)
            if choice in {"no", "n"}:
                print("[Prompt Check] 收到 no，继续后续流程。")
                return
            print("输入无效，请输入 yes 或 no。")

    def _load_abstract_maps_from_pack(
        self, pack_dir: str, ctx: BookGenerationContext
    ) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
        abstract_dir = os.path.join(pack_dir, "abstracts")
        chapter_abstracts_map: Dict[str, Dict[str, str]] = {}
        chapter_wiki_contents_map: Dict[str, Dict[str, str]] = {}
        if not os.path.isdir(abstract_dir):
            return chapter_abstracts_map, chapter_wiki_contents_map

        for chapter_key in ctx.sorted_chapters:
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            abstract_path = os.path.join(abstract_dir, f"{chapter_dir}.md")
            if not os.path.exists(abstract_path):
                continue
            abstracts, wiki_contents = self._load_abstract_file(abstract_path)
            chapter_abstracts_map[chapter_key] = abstracts
            chapter_wiki_contents_map[chapter_key] = wiki_contents
        return chapter_abstracts_map, chapter_wiki_contents_map

    def _load_qa_pairs_from_pack(self, pack_dir: str, ctx: BookGenerationContext) -> Dict[str, Dict[str, str]]:
        qa_pairs_dir = os.path.join(pack_dir, "qa_pairs")
        chapter_qa_pairs_map: Dict[str, Dict[str, str]] = {}
        if not os.path.isdir(qa_pairs_dir):
            return chapter_qa_pairs_map
        for chapter_key in ctx.sorted_chapters:
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            qa_pairs_path = os.path.join(qa_pairs_dir, f"{chapter_dir}.json")
            if not os.path.exists(qa_pairs_path):
                continue
            with open(qa_pairs_path, "r", encoding="utf-8") as f:
                qa_pairs = json.load(f)
            chapter_qa_pairs_map[chapter_key] = qa_pairs
        return chapter_qa_pairs_map

    def _list_practical_case_notebooks(self, pack_dir: str) -> List[str]:
        notebooks_root = os.path.join(pack_dir, "notebooks")
        if not os.path.isdir(notebooks_root):
            return []
        notebook_paths: List[str] = []
        for chapter_name in os.listdir(notebooks_root):
            if chapter_name == "data":
                continue
            chapter_dir = os.path.join(notebooks_root, chapter_name)
            if not os.path.isdir(chapter_dir):
                continue
            for filename in os.listdir(chapter_dir):
                if filename.endswith(".ipynb"):
                    notebook_paths.append(os.path.join(chapter_dir, filename))
        return notebook_paths

    async def _generate_practical_case_notebooks(self, pack_dir: str, ctx: BookGenerationContext) -> List[str]:
        practical_cases_path = os.path.join(ctx.book_info_dir, "practical_case.json")
        if not os.path.exists(practical_cases_path):
            print(f"[Practical Cases] 未找到案例定义文件，跳过：{practical_cases_path}")
            return []

        raw_text = self._read_file_safe(practical_cases_path)
        try:
            case_items = json.loads(raw_text)
        except Exception as e:
            print(f"[Practical Cases] 案例定义 JSON 解析失败，跳过：{e}")
            return []

        if not isinstance(case_items, list) or not case_items:
            print("[Practical Cases] practical_case.json 为空或格式非列表，跳过。")
            return []

        notebooks_root = self._get_pack_subdir(pack_dir, "notebooks")
        data_root = self._get_pack_subdir(notebooks_root, "data")
        prompt_template = self._load_prompt_template(pack_dir, "prompt_practical_case")
        notebook_paths: List[str] = []
        tasks: List[asyncio.Task] = []

        for idx, case in enumerate(case_items, start=1):
            if not isinstance(case, dict):
                continue
            # Respect chapter filter from main pipeline (e.g., chapter_ids=[1]).
            case_chapter_id = self._extract_case_chapter_id(case)
            if ctx.chapter_ids:
                if case_chapter_id is None:
                    print(
                        f"[Practical Cases] 无法识别案例所属章节，按 chapter_ids 过滤后跳过："
                        f"{case.get('chapter', '')} / {case.get('section', '')}"
                    )
                    continue
                if case_chapter_id not in ctx.chapter_ids:
                    continue

            chapter_name = str(case.get("chapter", f"chapter_{idx}")).strip() or f"chapter_{idx}"
            chapter_dir_name = sanitize_filename(chapter_name, max_len=80) or f"chapter_{idx}"
            chapter_root = self._get_pack_subdir(notebooks_root, chapter_dir_name)

            section = str(case.get("section", f"section_{idx}")).strip()
            topic = str(case.get("topic", f"topic_{idx}")).strip()
            case_slug = sanitize_filename(topic, max_len=100) or f"case_{idx:03d}"
            notebook_path = os.path.join(chapter_root, f"{case_slug}.ipynb")
            case_data_dir = os.path.join(data_root, chapter_dir_name, case_slug)
            data_dir_for_notebook = os.path.relpath(case_data_dir, start=chapter_root)

            if os.path.exists(notebook_path):
                print(f"[Practical Cases] 已存在 notebook，默认跳过：{notebook_path}")
                notebook_paths.append(notebook_path)
                continue
            tasks.append(
                asyncio.create_task(
                    self._generate_single_practical_case_notebook(
                        prompt_template=prompt_template,
                        case=case,
                        case_slug=case_slug,
                        notebook_path=notebook_path,
                        case_data_dir=case_data_dir,
                        data_dir_for_notebook=data_dir_for_notebook,
                    )
                )
            )

        if tasks:
            results = await asyncio.gather(*tasks)
            for generated_path in results:
                if generated_path:
                    notebook_paths.append(generated_path)

        return notebook_paths

    def _extract_case_chapter_id(self, case: Dict[str, Any]) -> Optional[int]:
        chapter_text = str(case.get("chapter", "")).strip()
        section_text = str(case.get("section", "")).strip()

        # Examples: "第1章 ...", "Chapter 2 ...", "章节3"
        m = re.search(r"(?:第\s*)?(\d+)\s*章", chapter_text, re.IGNORECASE)
        if not m:
            m = re.search(r"\bchapter\s*(\d+)\b", chapter_text, re.IGNORECASE)
        if m:
            return int(m.group(1))

        # Fallback: section like "1.2 ..." -> chapter id is 1
        m = re.search(r"\b(\d+)\s*[\.．]\s*\d+\b", section_text)
        if m:
            return int(m.group(1))

        return None

    async def _generate_single_practical_case_notebook(
        self,
        prompt_template: str,
        case: Dict[str, Any],
        case_slug: str,
        notebook_path: str,
        case_data_dir: str,
        data_dir_for_notebook: str,
    ) -> Optional[str]:
        async with self.practical_case_semaphore:
            try:
                notebook_payload = await self._build_practical_case_notebook_payload(
                    prompt_template=prompt_template,
                    case=case,
                    data_dir_for_notebook=data_dir_for_notebook,
                )
            except Exception as e:
                print(f"[Practical Cases] 案例生成失败，使用兜底 notebook：{case_slug}，原因：{e}")
                notebook_payload = {"notebook": self._build_fallback_notebook(case), "data_requirements": []}

            notebook_json = self._ensure_notebook_schema(notebook_payload.get("notebook"))
            with open(notebook_path, "w", encoding="utf-8") as f:
                json.dump(notebook_json, f, ensure_ascii=False, indent=2)

            self._write_case_data_assets(case_data_dir, case_slug, case, notebook_payload.get("data_requirements"))
            print(f"[Practical Cases] 已生成 notebook：{notebook_path}")
            return notebook_path

    async def _build_practical_case_notebook_payload(
        self, prompt_template: str, case: Dict[str, Any], data_dir_for_notebook: str
    ) -> Dict[str, Any]:
        if not prompt_template.strip():
            prompt_template = (
                "请基于输入案例生成一个可执行教学 notebook 的 JSON（ipynb 结构），"
                "并给出 data_requirements。输入：{{USER_INPUT_JSON}}，数据目录：{{DATA_DIR}}"
            )
        prompt = prompt_template.replace("{{USER_INPUT_JSON}}", json.dumps(case, ensure_ascii=False, indent=2))
        prompt = prompt.replace("{{DATA_DIR}}", data_dir_for_notebook.replace("\\", "/"))
        response = await gpt_completion(prompt)
        parsed = self._extract_json_object_from_text(response)
        if not isinstance(parsed, dict):
            return {"notebook": self._build_fallback_notebook(case), "data_requirements": []}
        if "notebook" not in parsed:
            parsed = {"notebook": parsed, "data_requirements": []}
        if not isinstance(parsed.get("data_requirements"), list):
            parsed["data_requirements"] = []
        return parsed

    def _extract_json_object_from_text(self, text: str) -> Any:
        if not text:
            return None
        candidate = text.strip()
        fenced = re.search(r"```json\s*([\s\S]*?)\s*```", candidate, re.IGNORECASE)
        if fenced:
            candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            snippet = candidate[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception:
                return None
        return None

    def _ensure_notebook_schema(self, notebook_obj: Any) -> Dict[str, Any]:
        if isinstance(notebook_obj, dict) and isinstance(notebook_obj.get("cells"), list):
            notebook_obj.setdefault("metadata", {})
            notebook_obj.setdefault("nbformat", 4)
            notebook_obj.setdefault("nbformat_minor", 5)
            notebook_obj["metadata"].setdefault(
                "kernelspec",
                {"display_name": "Python 3", "language": "python", "name": "python3"},
            )
            notebook_obj["metadata"].setdefault(
                "language_info",
                {"name": "python", "pygments_lexer": "ipython3"},
            )
            return notebook_obj
        return self._build_fallback_notebook({})

    def _build_fallback_notebook(self, case: Dict[str, Any]) -> Dict[str, Any]:
        chapter = case.get("chapter", "未命名章节")
        section = case.get("section", "未命名小节")
        topic = case.get("topic", "未命名案例")
        description = case.get("description", "")
        libs = case.get("key_libraries", [])
        libs_text = ", ".join(libs) if isinstance(libs, list) else str(libs)
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python", "pygments_lexer": "ipython3"},
            },
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": [
                        f"# {chapter} - {section}: {topic}\n\n",
                        "## 案例说明\n",
                        f"{description}\n\n",
                        f"建议库：`{libs_text}`\n",
                    ],
                },
                {
                    "cell_type": "code",
                    "metadata": {},
                    "execution_count": None,
                    "outputs": [],
                    "source": [
                        "# TODO: 在此补充可执行教学代码。\n",
                        "print('请根据案例说明补充实现。')\n",
                    ],
                },
            ],
        }

    def _write_case_data_assets(
        self,
        case_data_dir: str,
        case_slug: str,
        case: Dict[str, Any],
        data_requirements: Optional[List[Dict[str, Any]]],
    ) -> None:
        os.makedirs(case_data_dir, exist_ok=True)
        requirements = data_requirements if isinstance(data_requirements, list) else []
        if not requirements:
            requirements = [
                {
                    "name": "dataset_placeholder",
                    "mode": "download" if self._case_requires_download(case) else "construct",
                    "source": "",
                    "description": "如需外部数据集，请在此目录准备原始数据；若无则在 notebook 内构造。",
                }
            ]

        index_payload = {"case": case, "data_requirements": requirements}
        with open(os.path.join(case_data_dir, f"{case_slug}_data_requirements.json"), "w", encoding="utf-8") as f:
            json.dump(index_payload, f, ensure_ascii=False, indent=2)

        # 不在 data 目录写“手动下载说明”文档；下载逻辑统一放到 notebook 中与用户交互执行。
        has_construct = any(
            isinstance(req, dict) and str(req.get("mode", "download")).strip().lower() == "construct"
            for req in requirements
        )
        if has_construct:
            sample_csv_path = os.path.join(case_data_dir, f"{case_slug}_sample_dataset.csv")
            if not os.path.exists(sample_csv_path):
                with open(sample_csv_path, "w", encoding="utf-8") as f:
                    f.write("feature_1,feature_2,label\n0.1,0.2,0\n0.8,0.6,1\n")
        else:
            gitkeep_path = os.path.join(case_data_dir, ".gitkeep")
            if not os.path.exists(gitkeep_path):
                with open(gitkeep_path, "w", encoding="utf-8") as f:
                    f.write("")

    @staticmethod
    def _case_requires_download(case: Dict[str, Any]) -> bool:
        text = f"{case.get('topic', '')} {case.get('description', '')}".lower()
        keywords = ["下载", "api", "pubchem", "chembl", "pdb", "geo", "dataset", "数据集", "调用"]
        return any(k in text for k in keywords)

    @staticmethod
    def _dir_has_files(path: str) -> bool:
        return os.path.isdir(path) and any(os.scandir(path))

    @staticmethod
    def _clear_dir(path: str) -> None:
        if os.path.isdir(path):
            shutil.rmtree(path)

    @staticmethod
    def _ask_yes_no(prompt: str) -> bool:
        print(prompt)
        while True:
            choice = input("> ").strip().lower()
            if choice in {"yes", "y"}:
                return True
            if choice in {"no", "n"}:
                return False
            print("输入无效，请输入 yes 或 no。")

    @staticmethod
    def _extract_title_from_wiki_content(content: str) -> str:
        if not content:
            return ""
        for line in content.splitlines():
            title = line.strip()
            if title:
                return title
        return ""

    def _partial_fill_template(self, template: str, replacements: Dict[str, str]) -> str:
        pattern = re.compile(r"\{([a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]*)\}")

        def _replace(match: re.Match) -> str:
            key = match.group(1)
            value = replacements.get(key)
            if value:
                return str(value)
            return match.group(0)

        return pattern.sub(_replace, template)

    def _warn_missing_book_info_fields(self, course_info: Dict[str, str]) -> None:
        missing = []
        for _, field_name in self.COURSE_INFO_FIELD_MAP.items():
            value = str(course_info.get(field_name, "")).strip()
            if not value:
                missing.append(field_name)
        if missing:
            print(
                "[Warning] book_info.json 缺少或为空的字段："
                + "、".join(missing)
                + "。若需更强课程定制，请补充这些属性。"
            )

    @staticmethod
    def _read_file_safe(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def _write_pack_readme(self, pack_dir: str, course_name: str) -> None:
        readme_path = os.path.join(pack_dir, "README.md")
        content = f"""# 素材包说明（{course_name}）

本目录是教材生成流程的“素材包（pack）”输出，用于在生成正文前集中沉淀可复用素材，便于人工审核、修改与二次打包。

## 一、推荐目录结构（相对 `pack/`）

```text
book_info/
  syllabus.md
  book_info.json
  preface.md
  practical_case.json
prompts/
  prompt_abstract
  prompt_book
  prompt_book_step2
  prompt_book_step3
  prompt_preface
  prompt_select_project_qa
  draw_by_text
abstracts/
  第X章_xxx.md
wiki_articles/
  第X章_xxx/
    子章节目录/
      <title>.md
      index.json
qa_pairs/
  第X章_xxx.json
summary_images/
  第X章_xxx/
    summary.png
    images.json
notebooks/
  data/
    <topic>_data_requirements.json
    <topic>_sample_dataset.csv (按需)
  第X章_xxx/
    <topic>.ipynb
```

## 二、各目录作用与关键文件

- `book_info/`
  - `syllabus.md`：教材大纲（源文件清洗后版本）。
  - `book_info.json`：课程画像配置（受众、教学目标、行文风格等）。
  - `preface.md`：前言草稿。
  - `practical_case.json`：实战案例输入定义（notebook 生成来源）。

- `prompts/`
  - 课程定制后的提示词快照。
  - 策略为“文件级不覆盖”：已有文件跳过，不存在文件补齐。
  - 包含 `draw_by_text`，用于正文插图阶段的绘图提示词覆盖。
  - 便于人工改 prompt 后保持稳定，不被后续运行覆盖。

- `abstracts/`
  - 每章一个摘要文件，内部按子章节组织内容。
  - 用于后续正文生成时的知识主线控制。

- `wiki_articles/`
  - 子章节维度的外部参考资料沉淀。
  - `index.json` 记录该子章节下文章索引与文件映射。
  - 正文生成时可直接读取该目录内容，不重复在线检索。

- `qa_pairs/`
  - 章节问答对缓存（含检索结果与摘要字段）。
  - 用于项目/习题插入阶段，避免重复检索。

- `summary_images/`
  - 章节级概念图输出。
  - `images.json` 保存图像元数据（来源、章节映射等）。

- `notebooks/`
  - `第X章.../<topic>.ipynb`：按章节组织实战案例，文件名取 `topic`。
  - `data/`：统一数据目录，notebook 默认用 `../data` 读写。
  - 若 notebook 已存在，默认跳过并提示，不自动覆盖。

## 三、生成/重生成规则（交互式）

运行素材包生成时会分阶段询问：

1. `prompts`：按文件补齐，不整目录覆盖。
2. `preface`：若存在，询问是否重生成。
3. `abstracts`：若存在，询问是否重生成（重生会同步清理 `wiki_articles`）。
4. `summary_images`：若存在，询问是否重生成。
5. `qa_pairs`：若存在，询问是否重生成。
6. `notebooks`：是否执行“增量补齐”。执行后仅生成缺失文件，已存在 notebook 默认跳过，不清空目录。

## 四、正文插图提示词优先级

- 正文插图由 `draw_images.py` 调用时，提示词优先级如下：
  1. `pack/prompts/draw_by_text`
  2. 默认目录 `src/tools/draw_image/prompt/draw_by_text`
- 当 `prompt_dir` 指向 `pack/prompts` 但缺少其他绘图提示词（如 `get_insert_position`、`eval_image`）时，系统会自动回退到默认目录。

## 五、实战案例 notebook 规范

- 数据目录固定：`../data`（相对 notebook 路径）。
- 若需联网下载数据，下载逻辑必须在 notebook 内实现，并自动保存到 `../data`。
- 生成失败时会落兜底 notebook，避免流程中断。
- 目标是教学可读性：说明清晰、参数可调、输出可解释。

## 六、建议的人工审核顺序

1. `book_info/preface.md` 与 `book_info/book_info.json`
2. `prompts/`（尤其 `prompt_book`、`prompt_abstract`）
3. `abstracts/` 与 `summary_images/`
4. `qa_pairs/` 的覆盖质量
5. `notebooks/` 的可执行性与讲解质量

## 七、常见问题与排查

- **问：为什么某些 prompt 没更新？**  
  答：文件已存在会跳过。若需重建，删除对应文件后再运行。

- **问：正文绘图到底用了哪个提示词？**  
  答：优先使用 `pack/prompts/draw_by_text`；若不存在则回退到默认 `draw_image/prompt/draw_by_text`。

- **问：为什么 notebook 没重生成？**  
  答：实战案例采用不覆盖策略。已有 ipynb 会跳过；如需重建某个案例，请手动删除对应 ipynb 后重跑。

- **问：数据下载失败怎么办？**  
  答：优先在 notebook 中处理重试/镜像/兜底样本，不依赖手动文档下载。

## 八、版本管理建议

- 将 `pack/` 视为“可编辑中间层”。
- 建议至少纳入版本控制：
  - `book_info/`
  - `prompts/`
  - `abstracts/`
  - `notebooks/`
  - `README.md`
"""
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(content)
