"""Main entry point for the Topic Book Generator."""

import asyncio
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.topic_book_generator import TopicBookGenerator


async def main():
    """Main function to generate a book."""
    # Configuration
    language = "ch"  # Chinese - uses prompts/ directory
    # language = "en"  # English - uses prompts_en/ directory

    output_path = "./output"
    docs_path = "./docs"

    # Initialize the generator
    agent = TopicBookGenerator(language)

    # Book info: [education_level, course_name, number_of_topics, wiki_field_ids]
    if language == "ch":
        # book_info = ["研究生", "可控核聚变", "50", "860559", "1545472"]
        book_info = ["本科生", "离散数学", "50"]
    else:
        book_info = ["Master", "Controlled Nuclear Fusion", "50", "860559", "1545472"]

    # Define output paths
    # 根据语言选择输出目录：ch -> output, en -> output_en
    base_output = output_path if language == "ch" else f"{output_path}_en"
    chapter_save_path = f"{base_output}/chapter/{book_info[1]}.md"
    book_save_dir = f"{base_output}/books/{book_info[1]}"

    # Phase 1: Generate chapter outline
    print("=" * 50)
    print(f"Language: {language} (Using prompts directory: {'prompts/' if language == 'ch' else 'prompts_en/'})")
    print("Phase 1: Generating chapter outline...")
    print("=" * 50)
    # await agent.generate_chapter(book_info, chapter_save_path, docs_path)

    # Phase 2: Generate full book content
    print("\n" + "=" * 50)
    print("Phase 2: Generating book content...")
    print("=" * 50)
    prompt_config = {
        "course_type": "理论主导", # 理论主导，工程实践导向，理实融合，跨学科交叉
        "formal_density": "高", # 高，中，低 （是否要严谨的公式推导）
        "case_strategy": "本学科经典案例", # 本学科经典案例，多场景应用示例，历史演进案例
        "reader_level": "本科入门", # 本科入门，本科高阶，研究生，专业进阶
        "style_tendency": "严谨推演型", # 严谨推演型，叙事引导型，问题驱动型
    }   
    await agent.generate_book(
        chapter_save_path,
        book_save_dir,
        # chapter_ids=[1],  # Only process chapters 1, 2, 3, 4, 5, 6
        prompt_config=prompt_config,
    )

    print("\n" + "=" * 50)
    print("Book generation completed!")
    print("=" * 50)


if __name__ == '__main__':
    asyncio.run(main())
