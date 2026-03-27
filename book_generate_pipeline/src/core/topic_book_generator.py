"""Main topic book generator orchestrating the full pipeline."""

import os
import re
import json
import shutil
import asyncio
from typing import Dict, Any, Optional, List

from src.models import gemini_completion, gpt_completion, deepseek_completion, qwen_completion, doubao_completion
from src.core.chapter_generator import ChapterGenerator
from src.core.book_generator import BookGenerator
from src.core.material_pack_generator import MaterialPackGenerator
from src.core.chapter_types import ChapterInfo, SubChapterInfo, BookGenerationContext
from src.tools import md_to_html, html_to_pdf
from src.tools import draw_images_for_markdown
from src.utils import sanitize_filename



class TopicBookGenerator:
    """Main generator orchestrating the entire book generation pipeline."""

    def __init__(self, language: str = "cn"):
        self.gemini = gemini_completion
        self.gpt5 = gpt_completion
        self.deepseek = deepseek_completion
        self.qwen = qwen_completion
        self.doubao = doubao_completion

        self.chapter_generator = ChapterGenerator(language)
        self.material_pack_generator = MaterialPackGenerator(language)
        self.book_generator = BookGenerator(language)
        self.language = language
        self.battle_cnt = 0

        self.subchapter_semaphore = asyncio.Semaphore(20)
        self.chapter_semaphore = asyncio.Semaphore(7)

    async def _generate_single_subchapter(
        self,
        ctx: BookGenerationContext,
        chapter_key: str,
        sub_code: str,
        sub_info: SubChapterInfo
    ):
        """Generate content for a single subchapter."""
        async with self.subchapter_semaphore:
            sub_title = sub_info.subchapter_title
            filename = ctx.get_subchapter_filename(sub_code)
            output_path = os.path.join(ctx.get_chapter_step1_dir(chapter_key), filename)

            if os.path.exists(output_path):
                print(f"  [Skip step2] File already exists: {output_path}")
                return output_path

            try:
                article_content = await self.book_generator.generate_content(
                    ctx=ctx,
                    sub_info=sub_info,
                    sub_code=sub_code,
                    chapter_key=chapter_key
                )

                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(article_content)
                print(f"  [Success] Saved to {output_path}")
                return output_path

            except Exception as e:
                print(f"  [Error] Failed for {sub_code} ({sub_title}): {e}")
                return None

    async def _process_chapter_with_semaphore(
        self,
        ctx: BookGenerationContext,
        chapter_key: str,
        chapter_info: ChapterInfo
    ):
        """Process a chapter with project integration."""
        async with self.chapter_semaphore:
            chapter_title = chapter_info.title
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            print(f"\nProcessing Chapter {chapter_key} for project integration: {chapter_title}...")

            try:
                full_chapter_path = os.path.join(ctx.temp_md_dir, f"{chapter_dir}.md")
                
                if os.path.exists(full_chapter_path):
                    print(f"  [Skip step3] Chapter already exists: {full_chapter_path}")
                    return

                subchapter_file_paths = {}
                for sub_code in chapter_info.sub_chapters.keys():
                    if ctx.should_process_subchapter(sub_code):
                        filename = ctx.get_subchapter_filename(sub_code)
                        path = os.path.join(ctx.get_chapter_step1_dir(chapter_key), filename)
                        subchapter_file_paths[sub_code] = path

                articles_content, chapter_content, log_text = await self.book_generator.insert_project(
                    ctx=ctx,
                    chapter_info=chapter_info,
                    chapter_key=chapter_key,
                    subchapter_file_paths=subchapter_file_paths,
                )
                
                os.makedirs(os.path.dirname(full_chapter_path), exist_ok=True)
                with open(full_chapter_path, "w", encoding="utf-8") as f:
                    f.write(chapter_content)

                log_path = os.path.join(ctx.temp_log_dir, f"{chapter_dir}.md")
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(log_text)

                for full_title, optimized_content in articles_content.items():
                    code_match = re.match(r'^(\d+(?:\.\d+)*)\s+(.*)', full_title)
                    if code_match:
                        sub_code = code_match.group(1)
                        sub_title = code_match.group(2).strip()
                        if sub_code in ctx.filename_map["subchapters"]:
                            safe_title = ctx.filename_map["subchapters"][sub_code]
                        else:
                            safe_title = sanitize_filename(sub_title, 30)
                    else:
                        sub_code = "summary"
                        safe_title = "summary"

                    filename = f"Section_{sub_code.replace('.', '_')}_{safe_title}.md"
                    output_path = os.path.join(ctx.get_chapter_step2_dir(chapter_key), filename)
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(optimized_content)
                    print(f"  [Success] Updated {output_path}")

            except Exception as e:
                print(f"  [Error] Failed to process chapter {chapter_key}: {chapter_title}")
                print(f"  Error: {e}")

    async def generate_chapter(self, book_info, output_path: str, docs_path: str):
        """Generate chapter outline."""
        await self.chapter_generator.build_book_info(book_info, docs_path)
        prompt_chapter = self.chapter_generator.generate_prompt()
        print("Generating chapter...")
        res = await self.gemini(prompt_chapter)
        res = await self.chapter_generator.battle_syllabus(self.gpt5, self.doubao, res, 0)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'a', encoding="utf-8") as f:
            f.write("\n\n### 最终版 ###\n\n")
            f.write(res)
        print(f"[Done!] Chapter generated successfully! Saved to {output_path}")

    async def generate_book(
        self,
        chapter_path: str,
        output_dir: str,
        chapter_ids: Optional[List[int]] = None,
        subchapter_ids: Optional[List[str]] = None,
        prompt_config: Optional[Dict[str, str]] = None,
        preface_inputs: Optional[Dict[str, str]] = None,
    ):
        """Generate full book content using existing material pack."""
        ctx, _, _ = self._build_generation_context(
            chapter_path=chapter_path,
            output_dir=output_dir,
            chapter_ids=chapter_ids,
            subchapter_ids=subchapter_ids,
            prompt_config=prompt_config,
            preface_inputs=preface_inputs,
        )

        print(f"Parsed Course: {ctx.course_name}")

        print("\n[Phase 0] Loading material pack...")
        material_pack_result = self.material_pack_generator.load_material_pack(ctx)
        ctx.material_pack_dir = material_pack_result.get("material_pack_dir", "")
        ctx.chapter_abstracts_map = material_pack_result.get("chapter_abstracts_map", {})
        ctx.chapter_wiki_contents_map = material_pack_result.get("chapter_wiki_contents_map", {})
        if not os.path.isdir(ctx.material_pack_dir):
            raise FileNotFoundError(
                f"Material pack not found: {ctx.material_pack_dir}. "
                "Please run generate_material_pack(...) first."
            )
        print(f"[Phase 0 Done] Material pack loaded: {ctx.material_pack_dir}")

        print("\n[Phase 1] Generating subchapter content...")
        content_tasks = []
        for key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(key):
                continue
            chapter_info = ctx.book_structure[key]
            for sub_code, sub_info in chapter_info.sub_chapters.items():
                if not ctx.should_process_subchapter(sub_code):
                    continue
                content_tasks.append(
                    self._generate_single_subchapter(ctx, key, sub_code, sub_info)
                )

        file_paths = await asyncio.gather(*content_tasks)

        ctx.subchapter_file_paths_map = {}
        idx = 0
        for key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(key):
                continue
            chapter_info = ctx.book_structure[key]
            ctx.subchapter_file_paths_map[key] = {}
            for sub_code in chapter_info.sub_chapters.keys():
                if not ctx.should_process_subchapter(sub_code):
                    continue
                path = file_paths[idx]
                if path:
                    ctx.subchapter_file_paths_map[key][sub_code] = path
                idx += 1
        print("[Phase 1 Done]")

        # 当显式指定 subchapter_ids 时，通常用于“只生成部分小节正文(step1)”的场景：
        # 此时跳过后续的项目插入/整章纠错、插图与格式转换等步骤，以节省时间与成本。
        if ctx.subchapter_ids:
            print(
                "\n[Info] Detected subchapter_ids filter. "
                "Skipping Phase 2+ (project insertion/refine, images, md→html→pdf)."
            )
            return

        print("\n[Phase 2] Inserting projects and refining chapters...")
        chapter_tasks = []
        for key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(key):
                continue
            chapter_info = ctx.book_structure[key]
            chapter_tasks.append(
                self._process_chapter_with_semaphore(ctx, key, chapter_info)
            )
        await asyncio.gather(*chapter_tasks)
        print("[Phase 2 Done]")
        
        print("\n[Phase 3] Adding images to chapter content...")
        md_files_dir = ctx.temp_md_dir
        new_md_files_dir = ctx.temp_md_with_images_dir
        images_base_dir = ctx.images_dir
        image_tasks = []
        for key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(key):
                continue
            chapter_dir = ctx.get_chapter_dir(key)
            md_path = os.path.join(md_files_dir, f"{chapter_dir}.md")
            image_output_dir = os.path.join(images_base_dir, chapter_dir)
            new_md_path = os.path.join(new_md_files_dir, f"{chapter_dir}.md")
            image_tasks.append(
                draw_images_for_markdown(
                    md_path=md_path,
                    image_output_dir=image_output_dir,
                    new_md_path=new_md_path,
                )
            )
        if image_tasks:
            await asyncio.gather(*image_tasks)
        print("[Phase 3 Done]")
        
        md_files_dir = new_md_files_dir if os.path.isdir(new_md_files_dir) else md_files_dir
        html_files_dir = ctx.book_html_dir
        pdf_files_dir = ctx.book_pdf_dir
        os.makedirs(html_files_dir, exist_ok=True)
        os.makedirs(pdf_files_dir, exist_ok=True)
        await md_to_html(md_files_dir, html_files_dir)
        await html_to_pdf(html_files_dir, pdf_files_dir)

        print(f"\n[Done] All chapters for '{ctx.course_name}' have been processed.")

    async def generate_material_pack(
        self,
        chapter_path: str,
        output_dir: str,
        chapter_ids: Optional[List[int]] = None,
        subchapter_ids: Optional[List[str]] = None,
        prompt_config: Optional[Dict[str, str]] = None,
        preface_inputs: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Generate only material pack without book content generation."""
        ctx, resolved_preface_inputs, _ = self._build_generation_context(
            chapter_path=chapter_path,
            output_dir=output_dir,
            chapter_ids=chapter_ids,
            subchapter_ids=subchapter_ids,
            prompt_config=prompt_config,
            preface_inputs=preface_inputs,
        )
        print(f"Parsed Course: {ctx.course_name}")
        print("\n[Material Pack] Generating...")
        material_pack_result = await self.material_pack_generator.generate_material_pack(
            ctx=ctx,
            chapter_path=chapter_path,
            preface_inputs=resolved_preface_inputs,
        )
        print(f"[Material Pack Done] {material_pack_result.get('material_pack_dir', '')}")
        return material_pack_result

    def _build_generation_context(
        self,
        chapter_path: str,
        output_dir: str,
        chapter_ids: Optional[List[int]],
        subchapter_ids: Optional[List[str]],
        prompt_config: Optional[Dict[str, str]],
        preface_inputs: Optional[Dict[str, str]],
    ) -> tuple[BookGenerationContext, Dict[str, str], Dict[str, str]]:
        os.makedirs(output_dir, exist_ok=True)
        with open(chapter_path, 'r', encoding='utf-8') as f:
            chapter = f.read()
        syllabus_match = re.search(r'<syllabus>(.*?)</syllabus>', chapter, re.DOTALL)
        if not syllabus_match:
            raise ValueError("No <syllabus> tag found in chapter file.")
        syllabus = syllabus_match.group(1)
        syllabus_dict = self.parse_syllabus_to_dict(syllabus)
        course_name = syllabus_dict.get("course_name", "Unknown Course")
        book_structure_raw = syllabus_dict["book_structure"]
        book_structure = self._convert_book_structure(book_structure_raw)
        filename_map = syllabus_dict["filename_map"]
        sorted_chapters = sorted(
            book_structure.keys(),
            key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0
        )
        ctx = BookGenerationContext(
            course_name=course_name,
            book_structure=book_structure,
            book_structure_raw=book_structure_raw,
            filename_map=filename_map,
            sorted_chapters=sorted_chapters,
            prompt_config=prompt_config,
            chapter_ids=chapter_ids,
            subchapter_ids=subchapter_ids,
            output_dir=output_dir,
        )
        self._prepare_course_layout(ctx)
        book_info = self._save_book_info(ctx, chapter_path, preface_inputs, prompt_config)
        resolved_preface_inputs, resolved_prompt_config = self._resolve_prompt_inputs(
            course_info=book_info,
            preface_inputs=preface_inputs,
            prompt_config=prompt_config,
        )
        ctx.prompt_config = resolved_prompt_config
        return ctx, resolved_preface_inputs, resolved_prompt_config

    def _prepare_course_layout(self, ctx: BookGenerationContext) -> None:
        os.makedirs(ctx.pack_dir, exist_ok=True)
        os.makedirs(ctx.book_dir, exist_ok=True)
        os.makedirs(ctx.book_info_dir, exist_ok=True)

    def _save_book_info(
        self,
        ctx: BookGenerationContext,
        chapter_path: str,
        preface_inputs: Optional[Dict[str, str]],
        prompt_config: Optional[Dict[str, str]],
    ) -> Dict[str, str]:
        syllabus_target = os.path.join(ctx.book_info_dir, "syllabus.md")
        try:
            shutil.copy2(chapter_path, syllabus_target)
        except Exception as e:
            print(f"[Warning] Failed to copy syllabus to book_info: {e}")

        existing_info = self._read_book_info(ctx)
        preface_inputs = preface_inputs or {}
        prompt_config = prompt_config or {}
        info_payload = {
            "教材名称": ctx.course_name,
            "语言": existing_info.get("语言", "中文" if self.language == "ch" else "英文"),
            "面向人群": existing_info.get("面向人群", "{{面向人群}}"),
            "教学方式": existing_info.get("教学方式", "{{教学方式}}"),
            "教学目的": existing_info.get("教学目的", "{{教学目的}}"),
            "教学要求": existing_info.get("教学要求", "{{教学要求}}"),
            "教材行文风格": existing_info.get("教材行文风格", "{{教材行文风格}}"),
        }
        if preface_inputs.get("target_audience"):
            info_payload["面向人群"] = preface_inputs["target_audience"]
        if preface_inputs.get("teaching_methodology"):
            info_payload["教学方式"] = preface_inputs["teaching_methodology"]
        if preface_inputs.get("teaching_objectives"):
            info_payload["教学目的"] = preface_inputs["teaching_objectives"]
        if preface_inputs.get("teaching_requirements"):
            info_payload["教学要求"] = preface_inputs["teaching_requirements"]
        if prompt_config.get("style_tendency"):
            info_payload["教材行文风格"] = prompt_config["style_tendency"]

        info_path = os.path.join(ctx.book_info_dir, "book_info.json")
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info_payload, f, ensure_ascii=False, indent=2)
        return info_payload

    def _read_book_info(self, ctx: BookGenerationContext) -> Dict[str, str]:
        info_path = os.path.join(ctx.book_info_dir, "book_info.json")
        if not os.path.exists(info_path):
            return {}
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def _resolve_prompt_inputs(
        self,
        course_info: Dict[str, str],
        preface_inputs: Optional[Dict[str, str]],
        prompt_config: Optional[Dict[str, str]],
    ) -> tuple[Dict[str, str], Dict[str, str]]:
        preface_inputs = preface_inputs or {}
        prompt_config = prompt_config or {}
        resolved_preface_inputs = {
            "target_audience": preface_inputs.get("target_audience") or course_info.get("面向人群", "{{面向人群}}"),
            "teaching_methodology": preface_inputs.get("teaching_methodology") or course_info.get("教学方式", "{{教学方式}}"),
            "teaching_objectives": preface_inputs.get("teaching_objectives") or course_info.get("教学目的", "{{教学目的}}"),
            "teaching_requirements": preface_inputs.get("teaching_requirements") or course_info.get("教学要求", "{{教学要求}}"),
        }
        audience = course_info.get("面向人群", "")
        teaching_methodology = course_info.get("教学方式", "")
        style_tendency = prompt_config.get("style_tendency") or course_info.get("教材行文风格", "问题驱动型")
        resolved_prompt_config = {
            "course_type": prompt_config.get("course_type")
            or self._infer_course_type(teaching_methodology, style_tendency),
            "formal_density": prompt_config.get("formal_density")
            or self._infer_formal_density(style_tendency, audience),
            "case_strategy": prompt_config.get("case_strategy")
            or self._infer_case_strategy(teaching_methodology, style_tendency),
            "reader_level": prompt_config.get("reader_level")
            or self._infer_reader_level(audience),
            "style_tendency": style_tendency,
        }
        return resolved_preface_inputs, resolved_prompt_config

    @staticmethod
    def _infer_course_type(teaching_methodology: str, style_tendency: str) -> str:
        text = f"{teaching_methodology} {style_tendency}"
        if "跨学科" in text or "交叉" in text:
            return "跨学科交叉"
        if "实践" in text or "项目" in text or "实验" in text:
            if "理论" in text:
                return "理实融合"
            return "工程实践导向"
        return "理论主导"

    @staticmethod
    def _infer_formal_density(style_tendency: str, audience: str) -> str:
        if "严谨" in style_tendency:
            return "高"
        if "研究生" in audience or "博士" in audience:
            return "高"
        if "本科" in audience:
            return "中"
        return "中"

    @staticmethod
    def _infer_case_strategy(teaching_methodology: str, style_tendency: str) -> str:
        text = f"{teaching_methodology} {style_tendency}"
        if "历史" in text or "演进" in text:
            return "历史演进案例"
        if "实践" in text or "应用" in text or "项目" in text:
            return "多场景应用示例"
        return "本学科经典案例"

    @staticmethod
    def _infer_reader_level(audience: str) -> str:
        text = audience or ""
        if "研究生" in text or "硕士" in text or "博士" in text:
            return "研究生"
        if "工程师" in text or "从业" in text or "专业人员" in text:
            return "专业进阶"
        if "本科" in text and ("高年级" in text or "高阶" in text):
            return "本科高阶"
        if "本科" in text:
            return "本科入门"
        return "本科入门"

    def parse_syllabus_to_dict(self, syllabus_text: str) -> Dict[str, Any]:
        """Parse syllabus text into structured dictionary."""
        result = {
            "course_name": "",
            "book_structure": {},
            "filename_map": {
                "chapters": {},
                "subchapters": {}
            }
        }

        current_chapter_key = None
        current_subchapter_key = None
        lines = syllabus_text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('# '):
                result["course_name"] = line.replace('# ', '').strip()

            elif line.startswith('## '):
                full_chapter_title = line.replace('## ', '').strip()
                match = re.search(r'第(\d+)章', full_chapter_title)
                if match:
                    chapter_num = match.group(1)
                    chapter_key = f"chapter{chapter_num}"

                    result["book_structure"][chapter_key] = {
                        "title": full_chapter_title,
                        "sub_chapters": {}
                    }

                    safe_chapter_name = sanitize_filename(full_chapter_title, max_len=30)
                    result["filename_map"]["chapters"][chapter_key] = safe_chapter_name

                    current_chapter_key = chapter_key
                    current_subchapter_key = None

            elif line.startswith('### '):
                if current_chapter_key is None:
                    continue

                content = line.replace('### ', '').strip()
                parts = content.split(' ', 1)
                if len(parts) >= 2:
                    sub_code = parts[0].strip()
                    sub_title = parts[1].strip()

                    result["book_structure"][current_chapter_key]["sub_chapters"][sub_code] = {
                        "subchapter_title": sub_title,
                        "topics": []
                    }

                    safe_sub_name = sanitize_filename(sub_title, max_len=30)
                    result["filename_map"]["subchapters"][sub_code] = safe_sub_name

                    current_subchapter_key = sub_code

            elif line.startswith('- '):
                if current_chapter_key and current_subchapter_key:
                    topic_text = line.replace('- ', '').strip()
                    result["book_structure"][current_chapter_key]["sub_chapters"][current_subchapter_key]["topics"].append(topic_text)

        return result

    def _convert_book_structure(self, book_structure: Dict[str, Any]) -> Dict[str, ChapterInfo]:
        """Convert raw book structure dict to ChapterInfo objects."""
        return {
            chapter_key: ChapterInfo.from_dict(chapter_data)
            for chapter_key, chapter_data in book_structure.items()
        }


async def main():
    """Main entry point for testing."""
    language = "ch"
    output_path = "./output"
    docs_path = "./docs_input"

    agent = TopicBookGenerator(language)

    book_info = ["本科", "可控核聚变", "50"]

    course_dir = os.path.join(output_path, book_info[1])
    chapter_save_path = os.path.join(course_dir, "book_info", "syllabus.md")
    book_save_dir = course_dir

    await agent.generate_chapter(book_info, chapter_save_path, docs_path)
    await agent.generate_book(chapter_save_path, book_save_dir)


if __name__ == '__main__':
    asyncio.run(main())
