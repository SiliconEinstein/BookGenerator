"""Base classes for LLM providers."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, model_name: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str:
        """Generate completion for the given prompt."""
        pass

    @abstractmethod
    async def chat(self, messages: list, **kwargs) -> str:
        """Generate chat response."""
        pass


class LLMConfig:
    """Configuration for LLM providers."""

    def __init__(self, config_data: Dict[str, Any]):
        self.providers = config_data.get('providers', {})

    def get_provider_config(self, name: str) -> Dict[str, Any]:
        return self.providers.get(name, {})

    @property
    def mcp_url(self) -> str:
        return self.providers.get('mcp', {}).get('url', '')

    @property
    def wiki_search_api_base(self) -> str:
        return self.providers.get('wiki', {}).get('search_api_base', '')
