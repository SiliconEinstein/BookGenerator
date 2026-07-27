"""端到端自检：对一个极小课程跑完 material pack + 正文 + 插图 + 导出。"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from src.core.topic_book_generator import TopicBookGenerator

COURSE = "_e2e自检_分子对接入门"


async def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    course_dir = os.path.join("output", COURSE)
    syllabus = os.path.join(course_dir, "book_info", "syllabus.md")
    with open(os.path.join(course_dir, "book_info", "book_info.json"), encoding="utf-8") as f:
        info = json.load(f)

    agent = TopicBookGenerator("ch")
    prompt_config = {"style_tendency": info.get("教材行文风格", "问题驱动型")}
    preface_inputs = {
        "target_audience": info.get("面向人群", ""),
        "teaching_methodology": info.get("教学方式", ""),
        "teaching_objectives": info.get("教学目的", ""),
        "teaching_requirements": info.get("教学要求", ""),
    }

    if stage in {"all", "pack"}:
        print("\n########## STAGE: material pack ##########")
        await agent.generate_material_pack(
            syllabus, course_dir, prompt_config=prompt_config, preface_inputs=preface_inputs
        )

    if stage in {"all", "book"}:
        print("\n########## STAGE: book ##########")
        await agent.generate_book(
            syllabus, course_dir, prompt_config=prompt_config, preface_inputs=preface_inputs
        )

    print("\n########## DONE ##########")


if __name__ == "__main__":
    asyncio.run(main())
