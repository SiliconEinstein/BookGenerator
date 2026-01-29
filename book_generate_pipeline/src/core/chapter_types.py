"""Typed structures for chapter data."""

from dataclasses import dataclass
from typing import Dict, Any, List


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
