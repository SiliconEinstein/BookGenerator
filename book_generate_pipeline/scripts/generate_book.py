"""Script to generate a book from command line."""

import asyncio
import sys
import os
import argparse

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.core.topic_book_generator import TopicBookGenerator


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

    chapter_save_path = f"{output_path}/chapter/{language}/{course_name}.md"
    book_save_dir = f"{output_path}/books/{language}/{course_name}"

    # Generate chapter outline
    await agent.generate_chapter(book_info, chapter_save_path, docs_path)

    # Generate full book content
    await agent.generate_book(
        chapter_save_path,
        book_save_dir,
        chapter_ids=chapter_ids,
        subchapter_ids=subchapter_ids
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
