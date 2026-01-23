"""File helper utilities for path handling and sanitization."""

import os
import re
from pathlib import Path
from typing import Union


def sanitize_filename(name: str, max_len: int = 30) -> str:
    """
    Sanitize filename by removing illegal characters.

    Args:
        name: Original name to sanitize
        max_len: Maximum length of the resulting filename

    Returns:
        Sanitized filename (preserves Chinese, English, numbers, underscore, hyphen)
    """
    # Keep Chinese characters, English letters, numbers, underscores, and hyphens
    cleaned = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name)
    # Remove consecutive underscores
    cleaned = re.sub(r'_+', '_', cleaned)
    # Remove leading/trailing underscores
    cleaned = cleaned.strip('_')
    # Trim to max length
    return cleaned[:max_len] if cleaned else 'untitled'


def get_output_path(book_name: str, chapter: str = None, subchapter: str = None, step: str = None) -> Path:
    """
    Get standardized output path.

    Args:
        book_name: Name of the book
        chapter: Chapter directory name (optional)
        subchapter: Subchapter filename (optional)
        step: Step directory (step1, step2, step3) (optional)

    Returns:
        Path object pointing to the output location
    """
    base = Path('output/books') / sanitize_filename(book_name)

    if chapter:
        base = base / 'chapters' / sanitize_filename(chapter)
    if step:
        base = base / step
    if subchapter:
        base = base / sanitize_filename(subchapter)

    return base


def get_md_output_path(book_name: str, chapter: str = None) -> Path:
    """Get path for markdown output."""
    base = Path('output/books') / sanitize_filename(book_name) / 'md'
    if chapter:
        base = base / sanitize_filename(f"{chapter}.md")
    return base


def get_html_output_path(book_name: str) -> Path:
    """Get path for HTML output directory."""
    return Path('output/books') / sanitize_filename(book_name) / 'html'


def get_pdf_output_path(book_name: str) -> Path:
    """Get path for PDF output directory."""
    return Path('output/books') / sanitize_filename(book_name) / 'pdf'


def get_log_output_path(book_name: str, chapter: str) -> Path:
    """Get path for log output."""
    return Path('output/books') / sanitize_filename(book_name) / 'log' / sanitize_filename(f"{chapter}.md")


def ensure_dir(path: Union[str, Path]) -> Path:
    """Ensure a directory exists, creating if necessary."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_file_safe(path: Union[str, Path], encoding: str = 'utf-8') -> str:
    """Read file content safely, return empty string if file not found."""
    try:
        with open(path, 'r', encoding=encoding) as f:
            return f.read()
    except Exception:
        return ''


def write_file_safe(path: Union[str, Path], content: str, encoding: str = 'utf-8') -> bool:
    """Write file content safely."""
    try:
        ensure_dir(os.path.dirname(path))
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)
        return True
    except Exception:
        return False
