import sys
import os
import json
import re
import base64
import logging
from typing import Dict, List, Optional, Tuple, Union

import litellm

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


os.environ["LITELLM_PROXY_API_BASE"] = "http://8.219.58.57:4000"
os.environ["LITELLM_PROXY_API_KEY"] = "sk-WNrS8wC5RXbYvAx6KKdyEw"


class DrawImageAgent:
    def __init__(self) -> None:
        sys.path.append("F:/SciencePedia")
        self.model_gemini_2_5_pro = "litellm_proxy/gemini-2.5-pro"
        self.model_gemini_3_pro = "litellm_proxy/gemini-3-pro-preview"
        self.model_gemini_3_pro_image = "litellm_proxy/gemini-3-pro-image-preview"
        self.model_kwargs: Dict[str, object] = {}

    def get_article(self, article_id: int) -> Union[str, Tuple[str, str]]:
        return fetch_article_content(article_id)

    def get_prompt(self, prompt_path: str, prompt_name: str, content: Dict[str, str]) -> str:
        file_path = f"{prompt_path}/{prompt_name}"
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
        message = [{"role": "user", "content": prompt}]
        try:
            response = await litellm.acompletion(
                model=self.model_gemini_2_5_pro,
                messages=message,
                **self.model_kwargs,
            )
            if response.get("choices") and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"]
                content = self.parse_result(content)
                content = _fix_json_invalid_escapes(content)
                parsed = _try_parse_json(content)
                if isinstance(parsed, list):
                    return parsed
                logger.error("LLM response is not a list.")
                return []
            logger.error("No valid choices found in the response.")
            return []
        except Exception as exc:
            logger.exception(f"Error occurred while calling LLM API: {str(exc)}")
            return []

    async def produce_image(
        self, prompt: str, output_dir: str = "./output", image_name: str = "test.png"
    ) -> Optional[str]:
        first_path: Optional[str] = None
        try:
            response = await litellm.acompletion(
                model=self.model_gemini_3_pro_image,
                messages=[{"role": "user", "content": prompt}],
            )
            for i, img in enumerate(response.choices[0].message.images):
                img_url = img["image_url"]["url"]
                if "," in img_url:
                    base64_data = img_url.split(",", 1)[1]
                else:
                    raise ValueError("Invalid image URL format.")
                image_data = base64.b64decode(base64_data)
                if i > 0:
                    sub_name = image_name[:-4] + f"_{i}.png"
                else:
                    sub_name = image_name
                file_path = os.path.join(output_dir, sub_name)
                with open(file_path, "wb") as f:
                    f.write(image_data)
                if first_path is None:
                    first_path = file_path
            return first_path
        except Exception as exc:
            logger.exception(f"Error occurred while calling LLM API: {str(exc)}")
            return None

    def eval_image(self, image_path: str, prompt: str) -> Dict[str, object]:
        try:
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                        },
                    ],
                }
            ]
            response = litellm.completion(
                model=self.model_gemini_3_pro,
                messages=messages,
                max_tokens=4096,
            )
            response = response["choices"][0]["message"]["content"]
            response = self.parse_result(response)
            response = json.loads(response)
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
