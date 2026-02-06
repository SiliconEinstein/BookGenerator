"""Main topic book generator orchestrating the full pipeline."""

import os
import re
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from src.models import gemini_completion, gpt_completion, deepseek_completion, qwen_completion, doubao_completion
from src.core.chapter_generator import ChapterGenerator
from src.core.book_generator import BookGenerator
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
        self.book_generator = BookGenerator(language)
        self.language = language
        self.battle_cnt = 0

        self.abstract_semaphore = asyncio.Semaphore(20)
        self.subchapter_semaphore = asyncio.Semaphore(20)
        self.chapter_semaphore = asyncio.Semaphore(12)

    async def _generate_single_abstract(
        self,
        ctx: BookGenerationContext,
        chap_key: str,
        sub_code: str,
        sub_info: SubChapterInfo
    ):
        """Generate a single subchapter abstract."""
        async with self.abstract_semaphore:
            try:
                result = await self.book_generator.generate_abstract(
                    sub_title=sub_info.subchapter_title,
                    topics=sub_info.topics,
                    course_name=ctx.course_name,
                    sub_code=sub_code,
                    book_structure=ctx.book_structure_raw
                )
                return chap_key, sub_code, result['abstract'], result['wiki_content']
            except Exception as e:
                print(f"  [Warning] Failed to generate abstract for {sub_code}: {e}")
                return chap_key, sub_code, "[摘要生成失败]", ""

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
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            filename = ctx.get_subchapter_filename(sub_code)
            output_path = os.path.join(ctx.output_dir, chapter_dir, "step1", filename)

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
                full_chapter_path = os.path.join(ctx.output_dir, "md", f"{chapter_dir}.md")
                
                if os.path.exists(full_chapter_path):
                    print(f"  [Skip step3] Chapter already exists: {full_chapter_path}")
                    return

                subchapter_file_paths = {}
                for sub_code in chapter_info.sub_chapters.keys():
                    if ctx.should_process_subchapter(sub_code):
                        filename = ctx.get_subchapter_filename(sub_code)
                        path = os.path.join(ctx.output_dir, chapter_dir, "step1", filename)
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

                log_path = os.path.join(ctx.output_dir, "log", f"{chapter_dir}.md")
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
                    output_path = os.path.join(ctx.output_dir, chapter_dir, "step2", filename)
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
        with open(output_path, 'a', encoding="utf-8") as f:
            f.write("\n\n### 最终版 ###\n\n")
            f.write(res)
        print(f"[Done!] Chapter generated successfully! Saved to {output_path}")

    async def generate_abstracts(
        self,
        ctx: BookGenerationContext,
        chapter_key: str,
        chapter_info: ChapterInfo
    ) -> tuple:
        """Generate abstracts for all subchapters in a chapter.
        
        Returns:
            tuple: (abstracts: Dict[str, str], wiki_contents: Dict[str, str])
        """
        # 替换 /books/ 为 /abstract/ 以生成摘要路径
        abstract_base_dir = ctx.output_dir.replace("/books/", "/abstract/", 1)
        abstract_path = os.path.join(abstract_base_dir, f"{chapter_key}.md")

        if os.path.exists(abstract_path):
            print(f"  [Skip step1] Abstracts already exists: {abstract_path}")
            with open(abstract_path, "r", encoding="utf-8") as f:
                content = f.read()
            abstracts = {}
            wiki_contents = {}

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
            else:
                parts = content.split("### 子章节 ")
                for part in parts[1:]:
                    if ":" in part:
                        header, rest = part.split("：", 1) if "：" in part else part.split(":", 1)
                        sub_code = header.strip().split()[0]
                        abstracts[sub_code] = rest.strip()

            for match in re.finditer(
                r"<wiki_content([0-9.]+)>(.*?)</wiki_content\1>", content, re.DOTALL
            ):
                wiki_contents[match.group(1)] = match.group(2).strip()
            return abstracts, wiki_contents

        print(f"  [Generating Abstracts for {chapter_key}]")
        subchapter_tasks = []
        for sub_code, sub_info in chapter_info.sub_chapters.items():
            if ctx.should_process_subchapter(sub_code):
                subchapter_tasks.append(
                    self._generate_single_abstract(ctx, chapter_key, sub_code, sub_info)
                )

        results = await asyncio.gather(*subchapter_tasks)
        abstracts = {sub_code: abst for _, sub_code, abst, _ in results}
        wiki_contents = {sub_code: wiki for _, sub_code, _, wiki in results}

        os.makedirs(os.path.dirname(abstract_path), exist_ok=True)
        with open(abstract_path, "w", encoding="utf-8") as f:
            total_abstracts = ""
            total_wiki_contents = ""
            for sub_code, abst in abstracts.items():
                sub_title = chapter_info.sub_chapters[sub_code].subchapter_title
                wiki_content = wiki_contents.get(sub_code, "")
                total_abstracts += f"### 子章节 {sub_code}：{sub_title}\n"
                total_abstracts += f"{abst}\n\n"
                if wiki_content:
                    total_wiki_contents += f"<wiki_content{sub_code}>{wiki_content}</wiki_content{sub_code}>\n\n"
            f.write(f"<abstract>{total_abstracts}</abstract>\n\n")
            f.write(f"{total_wiki_contents}")
        print(f"  [Chapter Abstracts Saved] {abstract_path}")
        return abstracts, wiki_contents

    async def generate_book(
        self,
        chapter_path: str,
        output_dir: str,
        chapter_ids: Optional[List[int]] = None,
        subchapter_ids: Optional[List[str]] = None,
        prompt_config: Optional[Dict[str, str]] = None,
    ):
        """Generate full book content from chapter outline."""
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
            output_dir=output_dir
        )

        print(f"Parsed Course: {ctx.course_name}")

        print("\n[Phase 1] Generating abstracts...")
        chapter_abstracts_map = {}
        chapter_wiki_contents_map = {}
        for key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(key):
                continue
            chapter_info = ctx.book_structure[key]
            abstracts, wiki_contents = await self.generate_abstracts(ctx, key, chapter_info)
            chapter_abstracts_map[key] = abstracts
            chapter_wiki_contents_map[key] = wiki_contents
        print("[Phase 1 Done]")

        ctx.chapter_abstracts_map = chapter_abstracts_map
        ctx.chapter_wiki_contents_map = chapter_wiki_contents_map

        print("\n[Phase 2] Generating subchapter content...")
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
        print("[Phase 2 Done]")

        print("\n[Phase 3] Inserting projects and refining chapters...")
        chapter_tasks = []
        for key in ctx.sorted_chapters:
            if not ctx.should_process_chapter(key):
                continue
            chapter_info = ctx.book_structure[key]
            chapter_tasks.append(
                self._process_chapter_with_semaphore(ctx, key, chapter_info)
            )
        await asyncio.gather(*chapter_tasks)
        print("[Phase 3 Done]")
        
        # print("\n[Phase 4] Adding images to chapter content...")
        md_files_dir = os.path.join(ctx.output_dir, "md")
        new_md_files_dir = os.path.join(ctx.output_dir, "md_with_images")
        images_base_dir = ctx.output_dir.replace("books", "images")
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
        print("[Phase 4 Done]")
        
        md_files_dir = new_md_files_dir if os.path.isdir(new_md_files_dir) else md_files_dir
        html_files_dir = os.path.join(ctx.output_dir, "html")
        pdf_files_dir = os.path.join(ctx.output_dir, "pdf")
        os.makedirs(html_files_dir, exist_ok=True)
        os.makedirs(pdf_files_dir, exist_ok=True)
        await md_to_html(md_files_dir, html_files_dir)
        await html_to_pdf(html_files_dir, pdf_files_dir)

        print(f"\n[Done] All chapters for '{ctx.course_name}' have been processed.")

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

    chapter_save_path = f"{output_path}/chapter/{language}/{book_info[1]}.md"
    book_save_dir = f"{output_path}/books/{language}/{book_info[1]}"

    await agent.generate_chapter(book_info, chapter_save_path, docs_path)
    await agent.generate_book(chapter_save_path, book_save_dir)


if __name__ == '__main__':
    asyncio.run(main())
