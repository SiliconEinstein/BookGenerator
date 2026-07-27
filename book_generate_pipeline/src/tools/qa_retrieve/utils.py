import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from pydantic import BaseModel

from src.models import structured_completion

logger = logging.getLogger(__name__)


@dataclass
class LLMUsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    elapsed_time: float = 0.0
    model: str = ""

    def __str__(self):
        return (
            f"Model: {self.model} | "
            f"Tokens: {self.total_tokens} (prompt: {self.prompt_tokens}, completion: {self.completion_tokens}) | "
            f"Time: {self.elapsed_time:.2f}s"
        )


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    response_format: Optional[BaseModel] = None,
    temperature: float = 1.0,
    max_tokens: int = 4096,
    track_stats: bool = True,
    model: Optional[str] = None,
) -> Tuple[str, Optional[LLMUsageStats]]:
    """走 utility 角色模型的结构化输出调用。"""
    try:
        content, usage = await structured_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise

    if not track_stats:
        logger.info(f"Model returned successfully, elapsed time: {usage['elapsed_time']:.2f}s")
        return content, None

    stats = LLMUsageStats(
        model=usage["model"],
        elapsed_time=usage["elapsed_time"],
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
    )
    logger.info(f"Model returned successfully | {stats}")
    return content, stats
