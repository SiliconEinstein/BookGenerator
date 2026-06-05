from __future__ import annotations
import json
import re
from pathlib import Path

_INVALID_DIR_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def sanitize_course_dir_name(course_name: str) -> str:
    name = (course_name or '未命名课程').strip()
    name = _INVALID_DIR_CHARS.sub('_', name).strip('. ') or '未命名课程'
    return name[:200]
