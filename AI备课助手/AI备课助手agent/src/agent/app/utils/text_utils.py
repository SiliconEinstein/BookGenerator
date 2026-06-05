import re
from pathlib import Path

def normalize_whitespace(value: str) -> str:
    value = (value or '').replace('\r', '')
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r'\n{3,}', '\n\n', value)
    return value.strip()

def split_lines(value: str) -> list[str]:
    return [line.strip() for line in normalize_whitespace(value).split('\n') if line.strip()]

_META_LINE_PATTERNS = (
    re.compile(r'^课程结构'),
    re.compile(r'^目\s*录'),
    re.compile(r'^附\s*录'),
    re.compile(r'^第[一二三四五六七八九十\d\s]+部分\s'),
    re.compile(r'^[•o]\s', re.I),
)
_INTRO_LINE = re.compile(r'^绪论\s+(.+?)(?:[（(]\s*\d+\s*学时\s*[）)])?\s*$')
_SYLLABUS_TITLE = re.compile(r'^(.+?)(?:课程大纲|教学大纲|课程讲义)\s*$')
_GENERIC_COURSE = re.compile(r'^(.{2,40}?)(?:课程|专业课)\s*$')


def _is_meta_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in _META_LINE_PATTERNS)


def _course_name_from_source_path(source_path: str | None) -> str | None:
    if not source_path:
        return None
    stem = Path(source_path).stem.strip()
    if not stem or stem.lower() in {'sample-outline', 'source', 'outline'}:
        return None
    return stem


def extract_course_name(lines: list[str], source_path: str | None = None) -> str:
    scan = lines[:40]
    for line in scan:
        intro = _INTRO_LINE.match(line)
        if intro:
            name = intro.group(1).strip()
            if len(name) >= 4:
                return name
    for line in scan:
        title = _SYLLABUS_TITLE.match(line)
        if title:
            return title.group(1).strip()
    for line in scan:
        if _is_meta_line(line) or '课程结构' in line:
            continue
        generic = _GENERIC_COURSE.match(line)
        if generic and '大纲' not in line and '结构' not in line:
            return generic.group(1).strip()
        if any(token in line for token in ('课程大纲', '教学大纲')):
            return line.strip()
    hinted = _course_name_from_source_path(source_path)
    if hinted:
        return hinted
    for line in scan:
        if _is_meta_line(line) or len(line) < 4:
            continue
        if re.search(r'[\u4e00-\u9fffA-Za-z]{4,}', line):
            return line
    return lines[0] if lines else '未命名课程'


def to_chinese_chapter(index: int) -> str:
    numbers = ['一','二','三','四','五','六','七','八','九','十','十一','十二','十三','十四','十五']
    label = numbers[index - 1] if index - 1 < len(numbers) else str(index)
    return f'第{label}章'
