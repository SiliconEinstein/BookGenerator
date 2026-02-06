import re
from typing import List, Tuple


MARKER_PATTERN = re.compile(r"\(@images:[^)]+\)")
IMAGE_TAG_PATTERN = re.compile(r"<image\d+>[\s\S]*?</image\d+>")


def clean_line(text: str) -> str:
    text = MARKER_PATTERN.sub("", text)
    text = IMAGE_TAG_PATTERN.sub("", text)
    return text.strip()


def build_content_lines(markdown_text: str) -> List[str]:
    lines = []
    for line in markdown_text.splitlines():
        cleaned = clean_line(line)
        if cleaned:
            lines.append(cleaned)
    return lines


def build_numbered_content(markdown_text: str) -> Tuple[List[str], str]:
    content_lines = build_content_lines(markdown_text)
    numbered_lines = []
    for idx, line in enumerate(content_lines, start=1):
        numbered_lines.append(f"[{idx}]: {line}")
    return content_lines, "\n".join(numbered_lines)


def is_subsequence(needle: str, haystack: str) -> bool:
    i, j = 0, 0
    needle = needle.strip()
    haystack = haystack.strip()
    while i < len(needle) and j < len(haystack):
        if needle[i] == haystack[j]:
            i += 1
        j += 1
    return i == len(needle)


def find_insert_index(lines: List[str], position: str, start_index: int = 0) -> int:
    position = position.strip()
    for idx in range(start_index, len(lines)):
        if is_subsequence(position, lines[idx]):
            return idx
    return -1


def build_context_text(content_lines: List[str], indices: List[int]) -> str:
    if not indices:
        return ""
    context_lines = []
    for i in indices:
        if 1 <= i <= len(content_lines):
            context_lines.append(content_lines[i - 1])
    return "\n".join(context_lines).strip()
