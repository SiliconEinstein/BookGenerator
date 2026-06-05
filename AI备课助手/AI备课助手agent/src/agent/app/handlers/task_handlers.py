from __future__ import annotations
import re
from pathlib import Path
from app.config import OUTPUT_ROOT
from app.services.callback_service import send_task_callback
from app.services.content_service import create_section_content, refine_section_content
from app.services.oss_service import upload_file
from app.services.outline_service import load_text_from_file, parse_outline_from_text
from app.services.pdf_service import parse_pdf_source
from app.services.ppt_service import generate_ppt
from app.services.storage_service import storage_service
from app.utils.fs_utils import ensure_dir, read_json, sanitize_course_dir_name, write_json
from app.utils.outline_source_utils import (
    build_outline_markdown,
    load_input_markdown,
    markdown_to_plain_text,
    resolve_input_md_path,
    save_input_markdown,
)

async def handle_task(task: dict) -> str:
    task_type = task['taskType']
    if task_type == 0:
        return await _run_with_callback(task, _handle_outline_parse)
    if task_type == 1:
        return await _run_with_callback(task, _handle_section_generate)
    if task_type == 2:
        return await _run_with_callback(task, _handle_section_refine)
    if task_type == 3:
        return await _run_with_callback(task, _handle_ppt_generate)
    raise ValueError(f'Unsupported taskType: {task_type}')

async def _run_with_callback(task: dict, runner):
    try:
        result_url = await runner(task)
        send_task_callback(task.get('callbackUrl'), {'externalTaskId': task['externalTaskId'], 'status': 'success', 'resultUrl': result_url, 'errorMessage': ''})
        return result_url
    except Exception as error:
        send_task_callback(task.get('callbackUrl'), {'externalTaskId': task['externalTaskId'], 'status': 'failed', 'resultUrl': '', 'errorMessage': str(error)})
        raise

async def _resolve_outline_raw_text(payload: dict, config: dict, tmp_parser_dir: Path, external_id: str) -> tuple[str, str, str]:
    source_path = payload.get('sourceFileUrl') or config.get('sourceFileUrl') or ''
    source_type = payload.get('sourceType', 'txt')
    input_md_path = resolve_input_md_path(source_path)

    cached_md = load_input_markdown(input_md_path)
    if cached_md:
        return markdown_to_plain_text(cached_md), source_path, input_md_path

    if source_type == 'txt':
        raw_text = Path(source_path).read_text(encoding='utf-8')
    else:
        parser_result = parse_pdf_source(
            'url' if source_type == 'url' else 'file',
            source_path,
            tmp_parser_dir,
        )
        if not parser_result.get('parser_file'):
            raise RuntimeError('PDF parser output file not found')
        raw_text = load_text_from_file(parser_result['parser_file'])

    return raw_text, source_path, input_md_path


async def _handle_outline_parse(task: dict) -> str:
    payload = task.get('payload', {})
    config = task.get('config', {})
    tmp_parser_dir = OUTPUT_ROOT / '_tmp' / 'outline_parser' / (task.get('externalTaskId') or str(task['courseId']))
    ensure_dir(tmp_parser_dir)

    raw_text, source_path, input_md_path = await _resolve_outline_raw_text(payload, config, tmp_parser_dir, task.get('externalTaskId', ''))
    parsed = await parse_outline_from_text(raw_text, source_path)
    course_name = parsed['courseName']

    outline_source_url = save_input_markdown(
        input_md_path,
        build_outline_markdown(course_name, raw_text, source_path),
    )
    parsed['outlineSourceUrl'] = outline_source_url
    parsed['sourceFileUrl'] = source_path

    relative_path = 'outline/parsed.json'
    local_path = storage_service.resolve_course_path(course_name, relative_path)
    write_json(local_path, parsed)
    return _finalize_result(course_name, relative_path, local_path)


async def _handle_section_generate(task: dict) -> str:
    course_name = _resolve_course_name(task)
    payload = task.get('payload', {})
    config = task.get('config', {})
    outline_source = _read_outline_source(task, payload.get('outlineSourceUrl'))
    outline_context = _read_outline_parsed_context(task, payload.get('outlineContextUrl'))
    content = await create_section_content(
        payload['chapterName'],
        payload['sectionName'],
        int(config.get('sectionDuration', 45)),
        int(config.get('outputLanguage', 1)),
        outline_source,
        outline_context,
    )
    seq_no = int(payload.get('seqNo', 1))
    relative_path = f"sections/{payload['sectionId']}/seq_{seq_no}.json"
    local_path = storage_service.resolve_course_path(course_name, relative_path)
    write_json(local_path, content)
    return _finalize_result(course_name, relative_path, local_path)


async def _handle_section_refine(task: dict) -> str:
    course_name = _resolve_course_name(task)
    payload = task.get('payload', {})
    current_content = read_json(_to_local_path(payload['currentVersionUrl']))
    outline_source = _read_outline_source(task, payload.get('outlineSourceUrl'))
    outline_context = _read_outline_parsed_context(task, payload.get('outlineContextUrl'))
    refined = await refine_section_content(
        current_content,
        payload.get('instruction', ''),
        outline_source,
        outline_context,
    )
    next_seq = int(payload.get('nextSeqNo') or _infer_next_seq(payload['currentVersionUrl']))
    relative_path = f"sections/{payload['sectionId']}/seq_{next_seq}.json"
    local_path = storage_service.resolve_course_path(course_name, relative_path)
    write_json(local_path, refined)
    return _finalize_result(course_name, relative_path, local_path)


async def _handle_ppt_generate(task: dict) -> str:
    course_name = _resolve_course_name(task)
    payload = task.get('payload', {})
    config = task.get('config', {})
    content = read_json(_to_local_path(payload['contentVersionUrl']))
    section_id = payload['sectionId']
    relative_path = f'package/{section_id}/{section_id}.pptx'
    local_path = storage_service.resolve_course_path(course_name, relative_path)
    plan_path = storage_service.resolve_course_path(course_name, f'package/{section_id}/{section_id}.slides.json')
    await generate_ppt(
        local_path,
        content['chapterName'],
        content['sectionName'],
        content,
        int(config.get('outputLanguage', 1)),
        plan_output_path=plan_path,
    )
    return _finalize_result(course_name, relative_path, local_path)


def _finalize_result(course_name: str, relative_path: str, local_path: Path) -> str:
    course_dir = sanitize_course_dir_name(course_name)
    uploaded = upload_file(local_path, f'{course_dir}/{relative_path}')
    return uploaded or storage_service.to_result_url(course_name, relative_path)


def _to_local_path(url: str) -> Path:
    if url.startswith('file://'):
        return Path(url.removeprefix('file://'))
    path = Path(url)
    if path.exists():
        return path
    raise ValueError(f'Unsupported local result url: {url}')


def _infer_next_seq(url: str) -> int:
    match = re.search(r'seq_(\d+)\.json$', str(url))
    return int(match.group(1)) + 1 if match else 2


def _course_dir_from_path(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(OUTPUT_ROOT.resolve())
    except ValueError:
        return None
    if relative.parts and relative.parts[0] != '_tmp':
        return relative.parts[0]
    return None


def _resolve_course_name(task: dict) -> str:
    payload = task.get('payload', {})
    config = task.get('config', {})
    if raw := payload.get('courseName') or config.get('courseName'):
        return raw
    for key in ('outlineSourceUrl', 'outlineContextUrl', 'currentVersionUrl', 'contentVersionUrl'):
        url = payload.get(key)
        if not url:
            continue
        course_dir = _course_dir_from_path(_to_local_path(url))
        if course_dir:
            return course_dir
    raise ValueError('courseName is required in payload or config when it cannot be inferred from file URLs')


def _outline_source_url_from_task(task: dict) -> str | None:
    payload = task.get('payload', {})
    config = task.get('config', {})
    if url := payload.get('outlineSourceUrl') or config.get('outlineSourceUrl'):
        return url
    source = payload.get('sourceFileUrl') or config.get('sourceFileUrl')
    if source:
        return resolve_input_md_path(source)
    return None


def _read_outline_parsed_context(task: dict, outline_context_url: str | None) -> str:
    try:
        if outline_context_url:
            target = _to_local_path(outline_context_url)
        else:
            course_name = _resolve_course_name(task)
            target = storage_service.resolve_course_path(course_name, 'outline/parsed.json')
        return target.read_text(encoding='utf-8') if target.exists() else ''
    except Exception:
        return ''


def _read_outline_source(task: dict, outline_source_url: str | None) -> str:
    url = outline_source_url or _outline_source_url_from_task(task)
    if not url:
        raise ValueError('outlineSourceUrl or sourceFileUrl is required to locate input markdown')
    content = load_input_markdown(url)
    if content is None:
        raise FileNotFoundError(
            f'Input markdown not found: {url}. Run outline parse first to create it beside the source file.'
        )
    return content
