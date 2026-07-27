import os
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from src.models import generate_images, utility_completion, vision_completion

from .services.article_fetcher import fetch_article_content
from .pipelines.draw_by_text import generate_image_from_context
from .pipelines.draw_by_pedia_content import (
    build_pedia_markdown,
    draw_by_pedia_content as generate_pedia_by_id,
)
from .pipelines.draw_by_markdown import (
    generate_images_from_markdown as generate_markdown_images,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _fix_json_invalid_escapes(s: str) -> str:
    """修复 LLM 返回的 JSON 中非法反斜杠转义（如 C:\\Users、LaTeX \\in），使 json.loads 能通过。"""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in '"\\/bfnrt':
                result.append(s[i : i + 2])
                i += 2
            elif n == "u" and i + 5 <= len(s) and all(
                c in "0123456789abcdefABCDEF" for c in s[i + 2 : i + 6]
            ):
                result.append(s[i : i + 6])
                i += 6
            else:
                result.append("\\\\")
                result.append(s[i + 1])
                i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _try_parse_json(s: str):
    """解析 JSON，失败时尝试修复常见 LLM 错误（尾随逗号、缺失逗号等）再解析。"""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    repaired = s
    # 修复尾随逗号：,] -> ]，,} -> }
    repaired = re.sub(r",\s*]", "]", repaired)
    repaired = re.sub(r",\s*}", "}", repaired)
    # 修复缺失逗号：} 后紧跟 " 或 { 时补逗号（常见于对象成员之间）
    repaired = re.sub(r"}\s*(\")", r"}, \1", repaired)
    repaired = re.sub(r"}\s*(\{)", r"}, \1", repaired)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        raise


class DrawImageAgent:
    def __init__(self) -> None:
        self.model_kwargs: Dict[str, object] = {}

    def get_article(self, article_id: int) -> Union[str, Tuple[str, str]]:
        return fetch_article_content(article_id)

    def get_prompt(self, prompt_path: str, prompt_name: str, content: Dict[str, str]) -> str:
        file_path = Path(prompt_path) / prompt_name
        if not file_path.exists():
            # 允许调用方仅在 pack/prompts 中覆盖部分提示词，缺失项回退到默认目录。
            file_path = Path(__file__).resolve().parent / "prompt" / prompt_name
        with open(file_path, "r", encoding="utf-8") as f:
            prompt = f.read()
        for key, value in content.items():
            prompt = prompt.replace(key, value)
        return prompt

    def parse_result(self, response: str) -> str:
        match = re.search(r"```(?:json)?\s*([\s\S]*)\s*```", response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return response.strip()

    async def produce_response(self, prompt: str) -> List[Dict[str, object]]:
        try:
            content = await utility_completion(prompt, **self.model_kwargs)
            content = self.parse_result(content)
            content = _fix_json_invalid_escapes(content)
            parsed = _try_parse_json(content)
            if isinstance(parsed, list):
                return parsed
            logger.error("LLM response is not a list.")
            return []
        except Exception as exc:
            logger.exception(f"Error occurred while calling LLM API: {str(exc)}")
            return []

    async def produce_image(
        self, prompt: str, output_dir: str = "./output", image_name: str = "test.png"
    ) -> Optional[str]:
        """生成插图并落盘，返回首张图片路径；全部失败时返回 None。"""
        try:
            images = await generate_images(prompt=prompt)
        except Exception as exc:
            logger.error("出图失败 %s: %s", image_name, exc)
            return None

        first_path: Optional[str] = None
        for i, image_data in enumerate(images):
            sub_name = image_name if i == 0 else f"{image_name[:-4]}_{i}.png"
            file_path = os.path.join(output_dir, sub_name)
            with open(file_path, "wb") as f:
                f.write(image_data)
            if first_path is None:
                first_path = file_path
        return first_path

    async def eval_image(self, image_path: str, prompt: str) -> Dict[str, object]:
        try:
            response = await vision_completion(prompt, image_path)
            response = json.loads(self.parse_result(response))
            return {
                "describe": response.get("describe", ""),
                "reason": response.get("reason", ""),
                "score": response.get("score", -1),
            }
        except Exception as exc:
            logger.exception(f"Error occurred while calling LLM API: {str(exc)}")
            return {"describe": "", "reason": "", "score": -1}

    def build_pedia_markdown(self, main_content: str, applications: str) -> str:
        return build_pedia_markdown(main_content, applications)

    async def draw_by_text(
        self,
        context: str,
        output_dir: str,
        image_name: str,
        reason: Optional[str] = None,
        prompt_dir: str = "./prompt",
    ) -> str:
        return await generate_image_from_context(
            context=context,
            output_dir=output_dir,
            image_name=image_name,
            reason=reason,
            prompt_dir=prompt_dir,
            client=self,
        )

    async def draw_by_pedia_content(
        self,
        article_id: int,
        output_dir: str,
        prompt_dir: str = "./prompt",
    ) -> Dict[str, object]:
        return await generate_pedia_by_id(
            article_id=article_id,
            output_dir=output_dir,
            prompt_dir=prompt_dir,
            client=self,
        )

    async def draw_by_markdown(
        self,
        markdown_path: str,
        output_dir: str,
        prompt_dir: str = "./prompt",
        save_manifest: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        return await generate_markdown_images(
            markdown_path=markdown_path,
            output_dir=output_dir,
            prompt_dir=prompt_dir,
            save_manifest=save_manifest,
            client=self,
        )
