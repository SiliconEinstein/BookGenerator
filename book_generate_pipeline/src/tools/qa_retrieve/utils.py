import os
import time
import logging
import litellm
from dataclasses import dataclass
from typing import Optional, Tuple
from pydantic import BaseModel


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
    model: Optional[str] = None
) -> Tuple[str, Optional[LLMUsageStats]]:
    """
    Call large language model
    """
    if model is None:
        model = os.getenv("LLM_MODEL", "litellm_proxy/gemini-3-pro-preview")
    
    start_time = time.time()
    stats = None
    
    try:
        user_content = [
            {"type": "text", "text": user_prompt},
        ]
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        logger.info(f"Calling LLM: {model}")
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        elapsed_time = time.time() - start_time
        
        content = response['choices'][0]['message']['content']
        
        if track_stats:
            stats = LLMUsageStats(
                model=model,
                elapsed_time=elapsed_time
            )
            
            usage = None
            
            if 'usage' in response:
                usage = response['usage']
            elif '_hidden_params' in response and isinstance(response['_hidden_params'], dict):
                if 'usage' in response['_hidden_params']:
                    usage = response['_hidden_params']['usage']
            elif '_response_obj' in response and hasattr(response['_response_obj'], 'usage'):
                usage = response['_response_obj'].usage
                if hasattr(usage, '__dict__'):
                    usage = usage.__dict__
            
            if usage:
                if isinstance(usage, dict):
                    stats.prompt_tokens = usage.get('prompt_tokens', usage.get('input_tokens', 0))
                    stats.completion_tokens = usage.get('completion_tokens', usage.get('output_tokens', 0))
                    stats.total_tokens = usage.get('total_tokens', stats.prompt_tokens + stats.completion_tokens)
                else:
                    stats.prompt_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', 0))
                    stats.completion_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', 0))
                    stats.total_tokens = getattr(usage, 'total_tokens', stats.prompt_tokens + stats.completion_tokens)
            else:
                logger.warning("Unable to extract token usage information from response, model may not support it or response format differs")
                logger.debug(f"Response keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")
            
            logger.info(f"Model returned successfully | {stats}")
        else:
            logger.info(f"Model returned successfully, elapsed time: {elapsed_time:.2f}s")
        
        return content, stats
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"LLM call failed (elapsed time: {elapsed_time:.2f}s): {e}")
        raise

