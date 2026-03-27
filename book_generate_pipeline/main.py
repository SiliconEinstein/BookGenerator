"""Main entry point for the Topic Book Generator."""

import asyncio
import sys
import os
import json

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.topic_book_generator import TopicBookGenerator


REQUIRED_BOOK_INFO_FIELDS = [
    "教材名称",
    "语言",
    "面向人群",
    "教学方式",
    "教学目的",
    "教学要求",
    "教材行文风格",
]


def load_book_info(course_dir: str) -> dict:
    info_path = os.path.join(course_dir, "book_info", "book_info.json")
    if not os.path.exists(info_path):
        raise FileNotFoundError(f"book_info.json not found under: {course_dir}")
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_book_info_template(info_path: str, course_name: str, language: str) -> None:
    os.makedirs(os.path.dirname(info_path), exist_ok=True)
    template = {
        "教材名称": course_name,
        "语言": "中文" if language == "ch" else "英文",
        "面向人群": "",
        "教学方式": "",
        "教学目的": "",
        "教学要求": "",
        "教材行文风格": "",
    }
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)


def validate_book_info(book_info: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(book_info, dict):
        return ["book_info.json 必须是 JSON 对象。"]

    for field in REQUIRED_BOOK_INFO_FIELDS:
        value = str(book_info.get(field, "")).strip()
        if not value:
            errors.append(f"缺少或为空字段：{field}")
            continue
        if "{{" in value or "}}" in value:
            errors.append(f"字段包含未替换占位符：{field}")

    language = str(book_info.get("语言", "")).strip()
    if language and language not in {"中文", "英文"}:
        errors.append("字段“语言”仅支持“中文”或“英文”。")

    return errors


async def main():
    """Main function to generate a book."""
    # Configuration
    language = "ch"  # Chinese - uses prompts/ directory
    # language = "en"  # English - uses prompts_en/ directory

    output_path = "./output"
    # Initialize the generator
    agent = TopicBookGenerator(language)

    # 仅需指定课程名称，课程特征从 output/<课程名>/book_info/book_info.json 读取
    course_name = "人工智能辅助小分子药物设计"

    # Define output paths
    # 根据语言选择输出目录：ch -> output, en -> output_en
    base_output = output_path if language == "ch" else f"{output_path}_en"
    course_dir = os.path.join(base_output, course_name)
    book_info_path = os.path.join(course_dir, "book_info", "book_info.json")
    chapter_save_path = os.path.join(course_dir, "book_info", "syllabus.md")
    book_save_dir = course_dir

    if not os.path.isdir(course_dir):
        os.makedirs(course_dir, exist_ok=True)
        _write_book_info_template(book_info_path, course_name, language)
        print(f"[Init] 已创建课程目录：{course_dir}")
        print(f"[Action Needed] 请先完善教材信息：{book_info_path}")
        return

    if not os.path.exists(book_info_path):
        _write_book_info_template(book_info_path, course_name, language)
        print(f"[Action Needed] 未找到 book_info.json，已创建模板：{book_info_path}")
        print("[Action Needed] 请先填写完整教材信息后再运行。")
        return

    book_info = load_book_info(course_dir)
    validation_errors = validate_book_info(book_info)
    if validation_errors:
        print("[Action Needed] book_info.json 内容校验未通过，请完善后重试：")
        for err in validation_errors:
            print(f"  - {err}")
        print(f"[Path] {book_info_path}")
        return

    if not os.path.exists(chapter_save_path):
        raise FileNotFoundError(f"Syllabus file not found: {chapter_save_path}")

    print("=" * 50)
    print(f"Language: {language} (Using prompts directory: {'prompts/' if language == 'ch' else 'prompts_en/'})")
    print("=" * 50)

    # Phase 1: Generate material pack
    print("\n" + "=" * 50)
    print("Phase 1: Generating material pack...")
    print("=" * 50)
    prompt_config = {
        # 以下维度将由 book_info.json 的现有字段自动推断：
        # course_type / formal_density / case_strategy / reader_level
        "style_tendency": book_info.get("教材行文风格", "问题驱动型"),
    }
    preface_inputs = {
        "target_audience": book_info.get("面向人群", "{{面向人群}}"),
        "teaching_methodology": book_info.get("教学方式", "{{教学方式}}"),
        "teaching_objectives": book_info.get("教学目的", "{{教学目的}}"),
        "teaching_requirements": book_info.get("教学要求", "{{教学要求}}"),
    }
    await agent.generate_material_pack(
        chapter_save_path,
        book_save_dir,
        chapter_ids=[1],  # Only process chapters 1, 2, 3, 4, 5, 6
        prompt_config=prompt_config,
        preface_inputs=preface_inputs,
    )

    # print("\n" + "=" * 50)
    # print("Phase 2: Generating book content...")
    # print("=" * 50)
    # await agent.generate_book(
    #     chapter_save_path,
    #     book_save_dir,
    #     # chapter_ids=[1],
    #     prompt_config=prompt_config,
    #     preface_inputs=preface_inputs,
    # )

    # print("\n" + "=" * 50)
    # print("Book generation completed!")
    # print("=" * 50)


if __name__ == '__main__':
    asyncio.run(main())
