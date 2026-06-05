from __future__ import annotations
import json
import re
from pathlib import Path
from app.services.llm_service import gpt_completion, parse_json_object
from app.utils.prompt_utils import render_prompt
from app.utils.text_utils import split_lines, extract_course_name, to_chinese_chapter

chapter_regex = re.compile(r'^(第\s*[一二三四五六七八九十百零\d]+\s*章|Chapter\s+\d+|[一二三四五六七八九十]+、|\d+[\.、])\s*(.+)$', re.I)
section_regex = re.compile(r'^(第\s*[一二三四五六七八九十百零\d]+\s*节|\d+\.\d+|\(?[一二三四五六七八九十]\)|[A-Za-z]\.)\s*(.+)$')
part_regex = re.compile(r'^第[一二三四五六七八九十\d\s]+部分\s+(.+)$')
intro_section_regex = re.compile(r'^绪论\s+(.+?)(?:[（(]\s*\d+\s*学时\s*[）)])?\s*$')
MAX_OUTLINE_SOURCE_CHARS = 48000


def load_text_from_file(file_path: str | Path) -> str:
    return Path(file_path).read_text(encoding='utf-8')


async def parse_outline_from_text(raw_text: str, source_path: str | None = None) -> dict:
    trimmed = raw_text[:MAX_OUTLINE_SOURCE_CHARS]
    if len(raw_text) > MAX_OUTLINE_SOURCE_CHARS:
        trimmed += '\n\n[原文过长，以上为截断内容]'
    try:
        prompt = render_prompt(
            'outline_parse',
            source_text=trimmed,
            source_path_hint=source_path or '未知',
        )
        parsed = parse_json_object(await gpt_completion(prompt, temperature=0.2, max_tokens=8000))
        return _normalize_outline(parsed, raw_text, source_path)
    except Exception:
        return _parse_outline_by_rules(raw_text, source_path)


def _normalize_outline(parsed: dict, raw_text: str, source_path: str | None) -> dict:
    course_name = (parsed.get('courseName') or '').strip()
    if not course_name:
        course_name = extract_course_name(split_lines(raw_text), source_path)
    chapters = parsed.get('chapters') if isinstance(parsed.get('chapters'), list) else []
    normalized_chapters = []
    for index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            continue
        chapter_name = (chapter.get('chapterName') or f'第{index}章').strip()
        sections_raw = chapter.get('sections') if isinstance(chapter.get('sections'), list) else []
        sections = []
        for s_index, section in enumerate(sections_raw, start=1):
            if not isinstance(section, dict):
                continue
            section_name = (section.get('sectionName') or '').strip()
            if not section_name or section_name.startswith(('•', 'o ')):
                continue
            sections.append({'sectionName': section_name, 'sort': s_index})
        if sections:
            normalized_chapters.append({
                'chapterName': chapter_name,
                'sort': index,
                'sections': sections,
            })
    if not normalized_chapters:
        return _parse_outline_by_rules(raw_text, source_path)
    return {'courseName': course_name, 'chapters': normalized_chapters}


def _parse_outline_by_rules(raw_text: str, source_path: str | None = None) -> dict:
    lines = split_lines(raw_text)
    course_name = extract_course_name(lines, source_path)
    chapters = []
    current = None
    for line in lines:
        part_match = part_regex.match(line)
        if part_match:
            current = {
                'chapterName': f"{to_chinese_chapter(len(chapters) + 1)} {part_match.group(1).strip()}",
                'sort': len(chapters) + 1,
                'sections': [],
            }
            chapters.append(current)
            continue
        chapter_match = chapter_regex.match(line)
        if chapter_match:
            current = {
                'chapterName': f"{to_chinese_chapter(len(chapters) + 1)} {chapter_match.group(2).strip()}",
                'sort': len(chapters) + 1,
                'sections': [],
            }
            chapters.append(current)
            continue
        intro_match = intro_section_regex.match(line)
        if intro_match:
            if current is None:
                current = {
                    'chapterName': f"{to_chinese_chapter(len(chapters) + 1)} 绪论",
                    'sort': len(chapters) + 1,
                    'sections': [],
                }
                chapters.append(current)
            current['sections'].append({
                'sectionName': intro_match.group(1).strip(),
                'sort': len(current['sections']) + 1,
            })
            continue
        section_match = section_regex.match(line)
        if section_match:
            if current is None:
                current = {
                    'chapterName': f"{to_chinese_chapter(len(chapters) + 1)} 未分类章节",
                    'sort': len(chapters) + 1,
                    'sections': [],
                }
                chapters.append(current)
            current['sections'].append({
                'sectionName': section_match.group(2).strip(),
                'sort': len(current['sections']) + 1,
            })
    if not chapters:
        chunk_size = max(1, len(lines) // 3 or 1)
        for index in range(3):
            chunk = lines[index * chunk_size:(index + 1) * chunk_size]
            if not chunk:
                continue
            sections = [{'sectionName': item, 'sort': idx + 1} for idx, item in enumerate(chunk[1:4]) if not item.startswith(('•', 'o '))]
            if not sections:
                sections = [{'sectionName': f'{chunk[0]} 导学', 'sort': 1}]
            chapters.append({
                'chapterName': f"{to_chinese_chapter(index + 1)} {chunk[0]}",
                'sort': index + 1,
                'sections': sections,
            })
    return {'courseName': course_name, 'chapters': chapters}
