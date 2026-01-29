"""Chapter generator for creating book syllabi and outlines."""

import os
import re
import json
import asyncio
import pdfplumber
from dataclasses import dataclass
from typing import Dict, Any, Optional
from src.models import gemini_completion, gpt_completion, deepseek_completion, qwen_completion, doubao_completion
from src.tools import DatabaseManager
from src.utils import get_config


@dataclass
class BookInfo:
    """Structured book info."""
    education_level: str
    course_name: str
    number_of_topics: str
    wiki_field_content: Optional[str]
    job_requirements: str


class ChapterGenerator:
    """Generates chapter syllabi and handles syllabus refinement battles."""

    def __init__(self, language: str = "ch"):
        self.language = language
        self.config = get_config(language=language)

        self.prompt_chapter = self.config.get_prompt_name("chapter", "prompt_chapter")
        self.gemini = gemini_completion
        self.gpt5 = gpt_completion
        self.deepseek = deepseek_completion
        self.qwen = qwen_completion
        self.doubao = doubao_completion

        self.db_manager = DatabaseManager(llm_config={})
        self.get_field_index = self.db_manager.init_get_field_index_content()
        self.book_info: Optional[BookInfo] = None

        self.strategy = "auto"
        self.battle_cnt = 0

    async def build_book_info(self, book_info, docs_path: str):
        """Build book_info dictionary from input parameters."""
        if len(book_info) == 3:
            education_level, course_name, number_of_topics = book_info
            wiki_field_content = None
        elif len(book_info) > 3:
            education_level, course_name, number_of_topics = book_info[:3]
            node_ids = book_info[3:]
            wiki_field_content = ""
            for node_id in node_ids:
                try:
                    if self.language == "ch":
                        node_content, _ = await self._get_field_page_content(node_id, "zh-CN")
                    else:
                        _, node_content = await self._get_field_page_content(node_id, "en-US")
                    wiki_field_content += node_content + "\n"
                except Exception as e:
                    print(e)
                    continue

        # Read job requirements file
        job_file = os.path.join(docs_path, f"{course_name}_job.md")
        job_requirements = self._read_file_safe(job_file)

        self.book_info = BookInfo(
            education_level=education_level,
            course_name=course_name,
            number_of_topics=number_of_topics,
            wiki_field_content=wiki_field_content,
            job_requirements=job_requirements,
        )

    def generate_prompt(self) -> str:
        """Generate the prompt for chapter outline generation."""
        context_paper = ""
        self.prompt_chapter = self.config.get_prompt_name("chapter", "prompt_chapter")
        prompt_path = self.config.get_prompt_path(self.prompt_chapter)
        prompt = self._read_file_safe(prompt_path)
        if not self.book_info:
            raise ValueError("book_info is not initialized. Call build_book_info first.")
        prompt = prompt.format(
            course_name=self.book_info.course_name,
            education_level=self.book_info.education_level,
            wiki_field_content=self.book_info.wiki_field_content or '',
            language=self.language,
        )
        return context_paper + prompt

    def generate_battle_prompt(self, last_chapter: str) -> str:
        """Generate the prompt for syllabus refinement battle."""
        try:
            last_abstract, last_syllabus = last_chapter.split("<syllabus>")
            last_abstract = last_abstract.strip()
            last_syllabus = last_syllabus.split("</syllabus>")[0].strip()
        except Exception as e:
            print("Error splitting chapter into abstract and syllabus sections")
            last_abstract, last_syllabus = last_chapter, None

        prompt_battle_name = self.config.get_prompt_name("battle", "prompt_chapter_refine")
        prompt_path = self.config.get_prompt_path(prompt_battle_name)
        prompt_battle = self._read_file_safe(prompt_path)
        if not self.book_info:
            raise ValueError("book_info is not initialized. Call build_book_info first.")
        prompt_battle = prompt_battle.format(
            course_name=self.book_info.course_name,
            education_level=self.book_info.education_level,
            wiki_field_content=self.book_info.wiki_field_content,
            job_requirements=self.book_info.job_requirements,
            language=self.language,
            abstract=last_abstract,
            reference_syllabus=last_syllabus
        )
        return prompt_battle

    def generate_eval_prompt(self, last_chapter: str, curr_chapter: str) -> str:
        """Generate the evaluation prompt for comparing two syllabi."""
        prompt_eval_name = self.config.get_prompt_name("eval_chapter", "prompt_chapter_eval")
        prompt_path = self.config.get_prompt_path(prompt_eval_name)
        prompt_eval = self._read_file_safe(prompt_path)
        if not self.book_info:
            raise ValueError("book_info is not initialized. Call build_book_info first.")
        prompt_eval = prompt_eval.format(
            course_name=self.book_info.course_name,
            job_requirements=self.book_info.job_requirements,
            syllabus_a=last_chapter,
            syllabus_b=curr_chapter
        )
        return prompt_eval

    async def battle_syllabus(self, modelA, modelB, last_chapter: str, cnt: int = 0, tried_model=None) -> str:
        """Perform syllabus refinement battle between two models."""
        print(f"Starting round {cnt + 1} of battle")
        prompt_battle = self.generate_battle_prompt(last_chapter)
        curr_chapter = await modelB(prompt_battle)

        with open("output/last_chapter.md", 'w', encoding="utf-8") as f:
            f.write(curr_chapter)

        prompt_eval = self.generate_eval_prompt(last_chapter, curr_chapter)
        evaluators = [self.gemini, self.gpt5, self.deepseek, self.doubao]
        winner = await self._evaluate_syllabi(prompt_eval, evaluators)

        if winner == "B":
            return await self.battle_syllabus(modelB, modelA, curr_chapter, cnt + 1)
        elif winner == "A":
            new_tried = set(tried_model or [])
            model_id = getattr(modelB, '__name__', str(id(modelB)))
            new_tried.add(model_id)
            if len(new_tried) >= 2:
                print(f"Both models failed to refine chapter. Terminating at round {cnt}.")
                return last_chapter
            return await self.battle_syllabus(modelB, modelA, last_chapter, cnt + 1, tried_model=new_tried)
        else:
            print("No clear winner detected, restarting battle")
            return await self.battle_syllabus(modelB, modelA, last_chapter, cnt + 1)

    async def _evaluate_syllabi(self, prompt: str, evaluators) -> str:
        """Evaluate two syllabi using multiple evaluators."""
        if evaluators is None:
            raise ValueError("evaluators must be provided as a list of async model functions.")
        responses = await asyncio.gather(*[evaluator(prompt) for evaluator in evaluators])
        content = "\n# auto模式：\n"
        for i, response in enumerate(responses):
            content += f"evaluator{i}: {response}\n"
        self._save_result(content=content)
        winners = [self._parse_winner(r) for r in responses]
        return "A" if winners.count("A") >= winners.count("B") else "B"

    def _parse_winner(self, response: str) -> str:
        """Extract winner from response."""
        try:
            start = response.find("<result>")
            end = response.find("</result>")
            if start != -1 and end != -1 and start < end:
                winner = response[start + 8:end].strip()
                if winner in ("A", "B"):
                    return winner
        except Exception as e:
            if "A" in response[-15:]:
                return "A"
            elif "B" in response[-15:]:
                return "B"
        return "A"

    def _save_result(self, filepath: str = "output/eval_result.md", content: str = None):
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content)

    async def _get_field_page_content(self, page_id: str, language: str = "zh-CN") -> Optional[tuple]:
        """Get field page content from database."""
        page_info = {"page_type": "field", "page_id": page_id, "wiki_language": language}
        result = await self.get_field_index(page_info)

        def build_field_text(node, field_key: str, indent: int = 0) -> str:
            if not isinstance(node, dict):
                return ""
            value = node.get(field_key)
            lines = []
            if value is not None:
                value_str = str(value).strip()
                if value_str:
                    lines.append("  " * indent + "- " + value_str)
            child_nodes = node.get('child_nodes', [])
            if isinstance(child_nodes, list):
                for child in child_nodes:
                    child_text = build_field_text(child, field_key, indent + 1)
                    if child_text:
                        lines.append(child_text)
            return "\n".join(lines)

        root_node = result.get(int(page_id))
        if root_node:
            name_tree = build_field_text(root_node, 'node_name')
            seo_tree = build_field_text(root_node, 'seo_title')
        else:
            print("Root node not found in field_content.")
            name_tree, seo_tree = "", ""
        return name_tree, seo_tree

    def _read_file_safe(self, path: str) -> str:
        """Read file safely, return empty string if not found."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ""

    def extract_paper_text(self, paper_path: str) -> Optional[str]:
        """Extract text from PDF paper."""
        text_content = ""
        try:
            with pdfplumber.open(paper_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_content += text + "\n"
            return text_content
        except Exception as e:
            print(f"Failed to extract text from PDF: {e}")
            return None
