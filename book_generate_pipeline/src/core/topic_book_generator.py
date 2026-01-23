"""Main topic book generator orchestrating the full pipeline."""

import os
import re
import json
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from src.models import gemini_completion, gpt_completion, deepseek_completion, qwen_completion, doubao_completion
from src.core.chapter_generator import ChapterGenerator
from src.core.book_generator import BookGenerator
from src.tools import md_to_html, html_to_pdf
from src.utils import sanitize_filename


@dataclass
class BookGenerationContext:
    """Context for book generation process."""
    course_name: str
    structure_summary: Dict[str, Any]
    filename_map: Dict[str, Any]
    sorted_chapters: List[str]

    chapter_abstracts_map: Optional[Dict[str, Dict[str, str]]] = None
    chapter_wiki_contents_map: Optional[Dict[str, Dict[str, str]]] = None
    subchapter_file_paths_map: Optional[Dict[str, Dict[str, str]]] = None
    chapter_ids: Optional[List[int]] = None
    subchapter_ids: Optional[List[str]] = None
    output_dir: str = ""

    def get_chapter_dir(self, chapter_key: str) -> str:
        return self.filename_map["chapters"][chapter_key]

    def get_subchapter_filename(self, sub_code: str) -> str:
        safe_title = self.filename_map["subchapters"][sub_code]
        return f"Section_{sub_code.replace('.', '_')}_{safe_title}.md"

    def should_process_chapter(self, chapter_key: str) -> bool:
        if not self.chapter_ids:
            return True
        chapter_id = int(chapter_key.replace("chapter", "").strip())
        return chapter_id in self.chapter_ids

    def should_process_subchapter(self, sub_code: str) -> bool:
        if not self.subchapter_ids:
            return True
        return sub_code in self.subchapter_ids


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
        sub_info: dict
    ):
        """Generate a single subchapter abstract."""
        async with self.abstract_semaphore:
            try:
                result = await self.book_generator.generate_abstract(
                    sub_title=sub_info['subchapter_title'],
                    topics=sub_info['topics'],
                    course_name=ctx.course_name,
                    sub_code=sub_code,
                    structure_summary=ctx.structure_summary
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
        sub_info: dict
    ):
        """Generate content for a single subchapter."""
        async with self.subchapter_semaphore:
            sub_title = sub_info['subchapter_title']
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            filename = ctx.get_subchapter_filename(sub_code)
            output_path = os.path.join(ctx.output_dir, chapter_dir, "step1", filename)

            if os.path.exists(output_path):
                print(f"  [Skip] File already exists: {output_path}")
                return output_path

            try:
                article_content = await self.book_generator.generate_content(
                    sub_title=sub_title,
                    topics=sub_info['topics'],
                    course_name=ctx.course_name,
                    sub_code=sub_code,
                    structure_summary=ctx.structure_summary,
                    chapter_abstracts=ctx.chapter_abstracts_map.get(chapter_key, {}),
                    wiki_content=ctx.chapter_wiki_contents_map.get(chapter_key, {}).get(sub_code),
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
        chapter_info: dict
    ):
        """Process a chapter with project integration."""
        async with self.chapter_semaphore:
            chapter_title = chapter_info['title']
            chapter_dir = ctx.get_chapter_dir(chapter_key)
            print(f"\nProcessing Chapter {chapter_key} for project integration: {chapter_title}...")

            try:
                subchapter_file_paths = {}
                for sub_code in chapter_info['sub_chapters'].keys():
                    if ctx.should_process_subchapter(sub_code):
                        filename = ctx.get_subchapter_filename(sub_code)
                        path = os.path.join(ctx.output_dir, chapter_dir, "step1", filename)
                        subchapter_file_paths[sub_code] = path

                articles_content, chapter_content, log_text = await self.book_generator.insert_project(
                    course_name=ctx.course_name,
                    chapter_title=chapter_title,
                    chapter_structure=ctx.structure_summary,
                    sub_chapters=chapter_info['sub_chapters'],
                    subchapter_file_paths=subchapter_file_paths
                )

                full_chapter_path = os.path.join(ctx.output_dir, "md", f"{chapter_dir}.md")
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
        chapter_info: dict
    ) -> tuple:
        """Generate abstracts for all subchapters in a chapter.
        
        Returns:
            tuple: (abstracts: Dict[str, str], wiki_contents: Dict[str, str])
        """
        # 替换 /books/ 为 /abstract/ 以生成摘要路径
        abstract_base_dir = ctx.output_dir.replace("/books/", "/abstract/", 1)
        abstract_path = os.path.join(abstract_base_dir, f"{chapter_key}.md")

        if os.path.exists(abstract_path):
            print(f"  [Skip Abstracts] Already exists: {abstract_path}")
            with open(abstract_path, "r", encoding="utf-8") as f:
                content = f.read()
            abstracts = {}
            wiki_contents = {}
            parts = content.split("### 子章节 ")
            for part in parts[1:]:
                if ":" in part:
                    header, rest = part.split("：", 1) if "：" in part else part.split(":", 1)
                    sub_code = header.strip().split()[0]
                    # 解析 abstract 标签
                    abstract_match = re.search(r'<abstract>(.*?)</abstract>', rest, re.DOTALL)
                    # 解析 wiki_content 标签
                    wiki_match = re.search(rf'<wiki_content{sub_code}>(.*?)</wiki_content{sub_code}>', rest, re.DOTALL)
                    abstracts[sub_code] = abstract_match.group(1).strip() if abstract_match else rest.strip()
                    wiki_contents[sub_code] = wiki_match.group(1).strip() if wiki_match else ""
            return abstracts, wiki_contents

        print(f"  [Generating Abstracts for {chapter_key}]")
        subchapter_tasks = []
        for sub_code, sub_info in chapter_info['sub_chapters'].items():
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
                sub_title = chapter_info['sub_chapters'][sub_code]['subchapter_title']
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
        subchapter_ids: Optional[List[str]] = None
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
        structure_summary = syllabus_dict["structure_summary"]
        filename_map = syllabus_dict["filename_map"]
        sorted_chapters = sorted(
            structure_summary.keys(),
            key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0
        )

        ctx = BookGenerationContext(
            course_name=course_name,
            structure_summary=structure_summary,
            filename_map=filename_map,
            sorted_chapters=sorted_chapters,
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
            chapter_info = ctx.structure_summary[key]
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
            chapter_info = ctx.structure_summary[key]
            for sub_code, sub_info in chapter_info['sub_chapters'].items():
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
            chapter_info = ctx.structure_summary[key]
            ctx.subchapter_file_paths_map[key] = {}
            for sub_code in chapter_info['sub_chapters'].keys():
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
            chapter_info = ctx.structure_summary[key]
            chapter_tasks.append(
                self._process_chapter_with_semaphore(ctx, key, chapter_info)
            )
        await asyncio.gather(*chapter_tasks)

        md_files_dir = os.path.join(ctx.output_dir, "md")
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
            "structure_summary": {},
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

                    result["structure_summary"][chapter_key] = {
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

                    result["structure_summary"][current_chapter_key]["sub_chapters"][sub_code] = {
                        "subchapter_title": sub_title,
                        "topics": []
                    }

                    safe_sub_name = sanitize_filename(sub_title, max_len=30)
                    result["filename_map"]["subchapters"][sub_code] = safe_sub_name

                    current_subchapter_key = sub_code

            elif line.startswith('- '):
                if current_chapter_key and current_subchapter_key:
                    topic_text = line.replace('- ', '').strip()
                    result["structure_summary"][current_chapter_key]["sub_chapters"][current_subchapter_key]["topics"].append(topic_text)

        return result


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
