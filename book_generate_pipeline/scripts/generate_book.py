"""Script to generate a book from command line."""

import asyncio
import sys
import os
import argparse
import json

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.core.topic_book_generator import TopicBookGenerator


def load_book_info(course_dir: str) -> dict:
    info_path = os.path.join(course_dir, "book_info", "book_info.json")
    if not os.path.exists(info_path):
        return {}
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def generate_book(
    education_level: str,
    course_name: str,
    number_of_topics: str,
    language: str = "ch",
    chapter_ids: list = None,
    subchapter_ids: list = None,
):
    """Generate a book with the given parameters."""
    output_path = "./output"
    docs_path = "./docs"

    agent = TopicBookGenerator(language)
    book_info = [education_level, course_name, number_of_topics]

    course_dir = os.path.join(output_path, course_name)
    chapter_save_path = os.path.join(course_dir, "book_info", "syllabus.md")
    book_save_dir = course_dir
    if not os.path.exists(chapter_save_path):
        raise FileNotFoundError(f"Syllabus file not found: {chapter_save_path}")
    book_info_data = load_book_info(course_dir)
    prompt_config = {
        "style_tendency": book_info_data.get("教材行文风格", "问题驱动型"),
    }
    preface_inputs = {
        "target_audience": book_info_data.get("面向人群", "{{面向人群}}"),
        "teaching_methodology": book_info_data.get("教学方式", "{{教学方式}}"),
        "teaching_objectives": book_info_data.get("教学目的", "{{教学目的}}"),
        "teaching_requirements": book_info_data.get("教学要求", "{{教学要求}}"),
    }

    # Generate chapter outline
    await agent.generate_chapter(book_info, chapter_save_path, docs_path)

    # Generate material pack
    await agent.generate_material_pack(
        chapter_save_path,
        book_save_dir,
        chapter_ids=chapter_ids,
        subchapter_ids=subchapter_ids,
        prompt_config=prompt_config,
        preface_inputs=preface_inputs,
    )

    # Generate full book content (consume existing pack)
    await agent.generate_book(
        chapter_save_path,
        book_save_dir,
        chapter_ids=chapter_ids,
        subchapter_ids=subchapter_ids,
        prompt_config=prompt_config,
        preface_inputs=preface_inputs,
    )

    print(f"\nBook '{course_name}' generated successfully!")


def main():
    """Command line interface."""
    parser = argparse.ArgumentParser(description="Generate educational books using AI")
    parser.add_argument("--education-level", default="本科", help="Education level (e.g., 本科, 研究生)")
    parser.add_argument("--course-name", required=True, help="Course/book name")
    parser.add_argument("--number-of-topics", default="50", help="Number of topics")
    parser.add_argument("--language", default="ch", choices=["ch", "en"], help="Language (ch=en)")
    parser.add_argument("--chapter-ids", type=int, nargs="*", help="Specific chapter IDs to process")
    parser.add_argument("--subchapter-ids", nargs="*", help="Specific subchapter IDs to process")

    args = parser.parse_args()

    asyncio.run(generate_book(
        education_level=args.education_level,
        course_name=args.course_name,
        number_of_topics=args.number_of_topics,
        language=args.language,
        chapter_ids=args.chapter_ids,
        subchapter_ids=args.subchapter_ids,
    ))


if __name__ == "__main__":
    main()
