from __future__ import annotations
import re
from pathlib import Path
from app.config import OUTPUT_ROOT

MAX_OUTLINE_SOURCE_CHARS = 48000
_INPUT_MIRROR_DIR = OUTPUT_ROOT / '_input_mirror'


def is_local_source(source_path: str) -> bool:
    value = (source_path or '').strip()
    if not value:
        return False
    if value.startswith('file://'):
        value = value.removeprefix('file://')
    lowered = value.lower()
    return not lowered.startswith(('http://', 'https://', 'oss://', 's3://'))


def normalize_source_path(source_path: str) -> str:
    value = (source_path or '').strip()
    if value.startswith('file://'):
        return value.removeprefix('file://')
    return value


def resolve_input_md_path(source_path: str) -> str:
    """与源文件位于同一输入目录，扩展名改为 .md（本地或 OSS 逻辑路径）。"""
    source_path = normalize_source_path(source_path)
    if not source_path:
        raise ValueError('sourceFileUrl is required to resolve input markdown path')
    if is_local_source(source_path):
        return str(Path(source_path).with_suffix('.md'))
    if '/' in source_path:
        base, name = source_path.rsplit('/', 1)
        stem = Path(name).stem
        return f'{base}/{stem}.md'
    return f'{Path(source_path).stem}.md'


def _mirror_path(logical_md_path: str) -> Path:
    safe = re.sub(r'[^a-zA-Z0-9._-]+', '_', logical_md_path.strip('/'))
    return _INPUT_MIRROR_DIR / safe


def load_input_markdown(md_path: str) -> str | None:
    logical = normalize_source_path(md_path)
    if is_local_source(logical):
        path = Path(logical)
        if path.exists():
            return path.read_text(encoding='utf-8')
        return None
    mirror = _mirror_path(logical)
    if mirror.exists():
        return mirror.read_text(encoding='utf-8')
    return None


def save_input_markdown(md_path: str, content: str) -> str:
    logical = normalize_source_path(md_path)
    if is_local_source(logical):
        path = Path(logical)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return str(path.resolve())
    mirror = _mirror_path(logical)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(content, encoding='utf-8')
    return logical


def markdown_to_plain_text(md_content: str) -> str:
    lines = md_content.splitlines()
    body: list[str] = []
    skipped_header = False
    for line in lines:
        if not skipped_header and (line.startswith('#') or line.startswith('>')):
            continue
        if not skipped_header and not line.strip():
            continue
        skipped_header = True
        body.append(line)
    text = '\n'.join(body).strip()
    return text or md_content.strip()


def build_outline_markdown(course_name: str, raw_text: str, source_path: str | None = None) -> str:
    lines = [f'# {course_name}', '']
    if source_path:
        lines.extend([f'> 源文件：{source_path}', ''])
    lines.append(raw_text.strip())
    return '\n'.join(lines)


def trim_outline_source(text: str) -> str:
    if len(text) <= MAX_OUTLINE_SOURCE_CHARS:
        return text
    return text[:MAX_OUTLINE_SOURCE_CHARS] + '\n\n[原文过长，以上为截断内容]'
