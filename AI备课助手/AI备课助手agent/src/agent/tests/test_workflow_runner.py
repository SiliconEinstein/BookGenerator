import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.handlers.task_handlers import _to_local_path, handle_task
from app.services.storage_service import storage_service
from app.utils.fs_utils import read_json
from app.utils.outline_source_utils import resolve_input_md_path

ROOT = Path('/personal/AI备课助手')
DEFAULT_SOURCE_TEXT = '\n'.join([
    'Python程序设计课程大纲',
    '第一章 Python语言概述',
    '1.1 Python简介',
    '1.2 开发环境搭建',
    '第二章 基础语法',
    '2.1 变量与数据类型',
    '2.2 条件与循环',
])
DEMO_SECTION_NAME = '新药研发流程、成本与挑战'
DRUG_PDF_HINT = '药物设计'


def source_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == '.txt':
        return 'txt'
    if suffix in {'.pdf'}:
        return 'file'
    raise ValueError(f'Unsupported source file type: {path.suffix}')


def _default_section_target(source_file: Path) -> tuple[str, str]:
    if DRUG_PDF_HINT in source_file.stem or DRUG_PDF_HINT in str(source_file):
        return '绪论 人工智能与药物设计的发展', DEMO_SECTION_NAME
    return '第一章 Python语言概述', 'Python简介'


def find_section_in_parsed(parsed: dict, section_name: str) -> tuple[str, str] | None:
    for chapter in parsed.get('chapters', []):
        for section in chapter.get('sections', []):
            name = (section.get('sectionName') or '').strip()
            if name == section_name or section_name in name:
                return chapter.get('chapterName', '').strip(), name
    return None


def build_default_tasks(source_file: Path, course_id: int, section_id: int) -> list[dict[str, Any]]:
    chapter_name, section_name = _default_section_target(source_file)
    return [
        {
            'name': 'outline',
            'task': {
                'externalTaskId': f'task-outline-{course_id}-1',
                'taskType': 0,
                'courseId': course_id,
                'callbackUrl': '',
                'payload': {
                    'sourceType': source_type_for(source_file),
                    'sourceFileUrl': str(source_file),
                },
                'config': {},
            },
        },
        {
            'name': 'section',
            'task': {
                'externalTaskId': f'task-section-{course_id}-1',
                'taskType': 1,
                'courseId': course_id,
                'callbackUrl': '',
                'payload': {
                    'chapterName': chapter_name,
                    'sectionName': section_name,
                    'sectionId': section_id,
                    'seqNo': 1,
                },
                'config': {
                    'sectionDuration': 45,
                    'outputLanguage': 1,
                },
            },
        },
        {
            'name': 'refine',
            'task': {
                'externalTaskId': f'task-refine-{course_id}-1',
                'taskType': 2,
                'courseId': course_id,
                'callbackUrl': '',
                'payload': {
                    'sectionId': section_id,
                    'instruction': '请更突出应用场景',
                    'nextSeqNo': 2,
                },
                'config': {},
            },
        },
        {
            'name': 'ppt',
            'task': {
                'externalTaskId': f'task-ppt-{course_id}-1',
                'taskType': 3,
                'courseId': course_id,
                'callbackUrl': '',
                'payload': {
                    'sectionId': section_id,
                },
                'config': {},
            },
        },
    ]


def load_tasks_from_file(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('Task file must be a JSON array')
    return data


def should_run(step_name: str, selected_steps: set[str] | None) -> bool:
    return selected_steps is None or step_name in selected_steps


async def run_workflow(tasks: list[dict[str, Any]], selected_steps: set[str] | None = None) -> dict[str, str]:
    results: dict[str, str] = {}
    course_name: str | None = None
    outline_source_url: str | None = None
    outline_context_url: str | None = None
    demo_section: tuple[str, str] | None = None
    for item in tasks:
        step_name = item['name']
        if not should_run(step_name, selected_steps):
            print(f'[skip] {step_name}')
            continue

        task = json.loads(json.dumps(item['task']))
        payload = task.setdefault('payload', {})
        if course_name:
            payload['courseName'] = course_name
        if outline_source_url:
            payload['outlineSourceUrl'] = outline_source_url
        if outline_context_url:
            payload['outlineContextUrl'] = outline_context_url
        if step_name == 'section' and demo_section:
            payload['chapterName'], payload['sectionName'] = demo_section

        if step_name == 'refine' and 'currentVersionUrl' not in payload:
            previous = results.get('section')
            if not previous:
                raise ValueError('Refine step requires section resultUrl')
            payload['currentVersionUrl'] = previous

        if step_name == 'ppt' and 'contentVersionUrl' not in payload:
            previous = results.get('refine') or results.get('section')
            if not previous:
                raise ValueError('PPT step requires refine or section resultUrl')
            payload['contentVersionUrl'] = previous

        print(f'[run] {step_name}')
        result_url = await handle_task(task)
        results[step_name] = result_url
        print(f'[ok] {step_name}: {result_url}')
        if step_name == 'outline':
            parsed = read_json(_to_local_path(result_url))
            course_name = parsed.get('courseName')
            if course_name:
                print(f'[course] {course_name}')
                outline_source_url = parsed.get('outlineSourceUrl')
                if not outline_source_url:
                    source_in_task = item['task'].get('payload', {}).get('sourceFileUrl')
                    if source_in_task:
                        outline_source_url = resolve_input_md_path(source_in_task)
                outline_context_url = result_url
                matched = find_section_in_parsed(parsed, DEMO_SECTION_NAME)
                if matched:
                    demo_section = matched
                    print(f'[section-demo] {matched[0]} / {matched[1]}')
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description='Run controllable agent workflow tests')
    parser.add_argument('--steps', nargs='*', choices=['outline', 'section', 'refine', 'ppt'], help='Only run selected steps')
    parser.add_argument('--task-file', type=Path, help='Load task definitions from a JSON file')
    parser.add_argument('--course-id', type=int, default=101)
    parser.add_argument('--section-id', type=int, default=3001)
    parser.add_argument('--source-file', type=Path, default=ROOT / 'src' / 'agent' / 'tests' / 'sample-outline.txt', help='Outline source: .txt or .pdf (local path)')
    args = parser.parse_args()

    source_file = args.source_file
    if source_file.suffix.lower() == '.txt':
        source_file.parent.mkdir(parents=True, exist_ok=True)
        if not source_file.exists():
            source_file.write_text(DEFAULT_SOURCE_TEXT, encoding='utf-8')
    elif not source_file.exists():
        raise FileNotFoundError(f'Source file not found: {source_file}')

    tasks = load_tasks_from_file(args.task_file) if args.task_file else build_default_tasks(source_file, args.course_id, args.section_id)
    selected_steps = set(args.steps) if args.steps else None
    results = await run_workflow(tasks, selected_steps)
    print('workflow test finished')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
