"""Typed structures for chapter data."""

import os
from dataclasses import dataclass
from typing import Dict, Any, List, Optional



@dataclass
class SubChapterInfo:
    """Structured info for a single subchapter."""
    subchapter_title: str
    topics: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubChapterInfo":
        return cls(
            subchapter_title=data.get("subchapter_title", ""),
            topics=list(data.get("topics", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subchapter_title": self.subchapter_title,
            "topics": self.topics,
        }


@dataclass
class ChapterInfo:
    """Structured info for a chapter."""
    title: str
    sub_chapters: Dict[str, SubChapterInfo]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterInfo":
        raw_subs = data.get("sub_chapters", {}) or {}
        sub_chapters = {
            sub_code: SubChapterInfo.from_dict(sub_info)
            for sub_code, sub_info in raw_subs.items()
        }
        return cls(
            title=data.get("title", ""),
            sub_chapters=sub_chapters,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "sub_chapters": {code: info.to_dict() for code, info in self.sub_chapters.items()},
        }


@dataclass
class BookGenerationContext:
    """Context for book generation process."""
    course_name: str
    book_structure: Dict[str, ChapterInfo]
    book_structure_raw: Dict[str, Any]
    filename_map: Dict[str, Any]
    sorted_chapters: List[str]
    prompt_config: Optional[Dict[str, str]] = None
    
    chapter_abstracts_map: Optional[Dict[str, Dict[str, str]]] = None
    chapter_wiki_contents_map: Optional[Dict[str, Dict[str, str]]] = None
    subchapter_file_paths_map: Optional[Dict[str, Dict[str, str]]] = None
    chapter_ids: Optional[List[int]] = None
    subchapter_ids: Optional[List[str]] = None
    output_dir: str = ""
    material_pack_dir: str = ""

    # -------- unified course layout --------
    # course_dir/
    #   pack/...
    #   book/{chapters,md,md_with_images,log,qa_pairs,images,html,pdf}/...
    #   book_info/{syllabus.md,book_info.json}

    @property
    def course_dir(self) -> str:
        """Root dir for a single course (course_name folder)."""
        return self.output_dir

    @property
    def pack_dir(self) -> str:
        return os.path.join(self.course_dir, "pack")

    @property
    def book_dir(self) -> str:
        return os.path.join(self.course_dir, "book")

    @property
    def book_info_dir(self) -> str:
        return os.path.join(self.course_dir, "book_info")

    @property
    def chapters_dir(self) -> str:
        return os.path.join(self.book_dir, "chapters")

    @property
    def temp_md_dir(self) -> str:
        return os.path.join(self.book_dir, "md")

    @property
    def temp_md_with_images_dir(self) -> str:
        return os.path.join(self.book_dir, "md_with_images")

    @property
    def temp_log_dir(self) -> str:
        return os.path.join(self.book_dir, "log")

    @property
    def temp_qa_pairs_dir(self) -> str:
        return os.path.join(self.book_dir, "qa_pairs")

    @property
    def book_html_dir(self) -> str:
        return os.path.join(self.book_dir, "html")

    @property
    def book_pdf_dir(self) -> str:
        return os.path.join(self.book_dir, "pdf")

    @property
    def images_dir(self) -> str:
        return os.path.join(self.book_dir, "images")

    def get_chapter_dir(self, chapter_key: str) -> str:
        return self.filename_map["chapters"][chapter_key]

    def get_chapter_root_dir(self, chapter_key: str) -> str:
        """Directory for a chapter under chapters/."""
        return os.path.join(self.chapters_dir, self.get_chapter_dir(chapter_key))

    def get_chapter_step1_dir(self, chapter_key: str) -> str:
        return os.path.join(self.get_chapter_root_dir(chapter_key), "step1")

    def get_chapter_step2_dir(self, chapter_key: str) -> str:
        return os.path.join(self.get_chapter_root_dir(chapter_key), "step2")

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
