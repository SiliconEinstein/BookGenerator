import json
from app.services.llm_service import gpt_completion, parse_json_object
from app.utils.outline_source_utils import trim_outline_source
from app.utils.prompt_utils import render_prompt

_SECTION_FIELDS = ('chapterName', 'sectionName', 'teachingGoal', 'knowledgePoints', 'suggestedStructure', 'extraInfo')


def _language_label(output_language: int) -> str:
    return '英文' if output_language == 2 else '中文'


async def create_section_content(
    chapter_name: str,
    section_name: str,
    section_duration: int = 45,
    output_language: int = 1,
    outline_source: str = '',
    outline_context: str = '',
) -> dict:
    if not outline_source.strip():
        raise ValueError('outline_source is required for section generation')
    prompt = render_prompt(
        'section_generate',
        outline_source=trim_outline_source(outline_source),
        outline_context=outline_context or '无',
        chapter_name=chapter_name,
        section_name=section_name,
        section_duration=str(section_duration),
        output_language_label=_language_label(output_language),
    )
    try:
        result = parse_json_object(await gpt_completion(prompt, temperature=0.4, max_tokens=4000))
        return _normalize_section(result, chapter_name, section_name)
    except Exception:
        return fallback_create(chapter_name, section_name, section_duration, output_language)


async def refine_section_content(
    current_content: dict,
    instruction: str,
    outline_source: str = '',
    outline_context: str = '',
) -> dict:
    prompt = render_prompt(
        'section_refine',
        outline_source=trim_outline_source(outline_source) if outline_source.strip() else '无',
        outline_context=outline_context or '无',
        current_content=json.dumps(current_content, ensure_ascii=False, indent=2),
        instruction=instruction or '保持原样',
    )
    try:
        result = parse_json_object(await gpt_completion(prompt, temperature=0.4, max_tokens=4000))
        return _normalize_section(
            result,
            current_content.get('chapterName', ''),
            current_content.get('sectionName', ''),
        )
    except Exception:
        return fallback_refine(current_content, instruction)


def _normalize_section(content: dict, chapter_name: str, section_name: str) -> dict:
    normalized = {
        'chapterName': (content.get('chapterName') or chapter_name).strip(),
        'sectionName': (content.get('sectionName') or section_name).strip(),
    }
    for field in _SECTION_FIELDS[2:]:
        normalized[field] = str(content.get(field) or '').strip()
    return normalized


def fallback_create(chapter_name: str, section_name: str, section_duration: int, output_language: int) -> dict:
    prefix = 'EN' if output_language == 2 else 'CN'
    return {
        'chapterName': chapter_name,
        'sectionName': section_name,
        'teachingGoal': f'{prefix}：围绕“{section_name}”建立清晰认知，理解本节在{chapter_name}中的定位，并完成约{section_duration}分钟的学习目标。',
        'knowledgePoints': f'{prefix}：1. {section_name} 的基本概念；2. {section_name} 与课程整体知识链路的关系；3. {section_name} 的典型应用或实践场景。',
        'suggestedStructure': f'{prefix}：建议采用“问题导入 -> 核心概念讲解 -> 示例分析 -> 小结回顾”的教学结构。',
        'extraInfo': f'{prefix}：可结合课程原始大纲中的表述进行二次编辑，重点保持与原课程知识边界一致。',
    }


def fallback_refine(current_content: dict, instruction: str) -> dict:
    suffix = f' 微调要求：{instruction}' if instruction else ''
    return {
        **current_content,
        'teachingGoal': f"{current_content.get('teachingGoal', '')}{suffix}",
        'knowledgePoints': f"{current_content.get('knowledgePoints', '')}{suffix}",
        'suggestedStructure': f"{current_content.get('suggestedStructure', '')}{suffix}",
        'extraInfo': f"{current_content.get('extraInfo', '')}{suffix}",
    }
