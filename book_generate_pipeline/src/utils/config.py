"""Configuration management for the project."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """Configuration manager with environment variable support."""

    _instance = None
    _config_cache: Dict[str, Any] = {}

    def __new__(cls, env: str = 'dev', language: str = 'ch'):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, env: str = 'dev', language: str = 'ch'):
        if not hasattr(self, '_initialized') or not self._initialized:
            self.env = env
            self.language = language
            self._load_config()
            self._initialized = True

    def set_language(self, language: str):
        """Set the language for prompts directory selection."""
        self.language = language

    def _load_config(self):
        """Load configuration from YAML file."""
        config_dir = Path(__file__).parent.parent.parent / 'config'
        config_file = config_dir / f'config.{self.env}.yaml'

        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                self._config_cache = yaml.safe_load(f) or {}
        else:
            self._config_cache = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'llm': {
                'providers': {
                    'gemini': {
                        'model': 'litellm_proxy/gemini-3-pro-preview',
                        'base_url': os.environ.get('LITELLM_PROXY_API_BASE', 'http://8.219.58.57:4000'),
                        'api_key': os.environ.get('LITELLM_API_KEY', 'sk-WNrS8wC5RXbYvAx6KKdyEw'),
                    },
                    'gpt5': {
                        'model': 'Vendor2/GPT-5.2',
                        'base_url': 'https://api.gpugeek.com/v1',
                        'api_key': os.environ.get('GPUGEEK_API_KEY', ''),
                    },
                    'deepseek': {
                        'model': 'DeepSeek/DeepSeek-V3-0324',
                    },
                    'qwen': {
                        'model': 'GpuGeek/Qwen3-VL-30B-A3B-Thinking',
                    },
                    'doubao': {
                        'model': 'Volcengine/Doubao-Seed-1.6',
                    },
                }
            },
            'mcp': {
                'url': 'http://rceb1397946.bohrium.tech:50001/sse',
            },
            'wiki': {
                'search_api_base': 'https://literature-sage.test.bohrium.com',
            },
            'output': {
                'base_dir': 'output/books',
                'temp_dir': 'output/temp',
            },
            'prompts': {
                'base_dir_ch': 'prompts',  # Chinese prompts directory
                'base_dir_en': 'prompts_en',  # English prompts directory
            },
        }

    @property
    def mcp_url(self) -> str:
        """Get MCP server URL."""
        return self._config_cache.get('mcp', {}).get('url', '')

    @property
    def wiki_search_api_base(self) -> str:
        """Get wiki search API base URL."""
        return self._config_cache.get('wiki', {}).get('search_api_base', '')

    def get_provider_config(self, name: str) -> Dict[str, Any]:
        """Get configuration for a specific LLM provider."""
        return self._config_cache.get('llm', {}).get('providers', {}).get(name, {})

    @property
    def output_base_dir(self) -> Path:
        """Get base output directory."""
        return Path(self._config_cache.get('output', {}).get('base_dir', 'output/books'))

    @property
    def prompts_base_dir(self) -> Path:
        """Get prompts base directory based on language setting."""
        prompts_config = self._config_cache.get('prompts', {})
        # Use language-specific directory: prompts for 'cn', prompts_en for 'en'
        base_dir = prompts_config.get('base_dir_en', 'prompts_en') if self.language == 'en' else prompts_config.get('base_dir_ch', 'prompts')
        return Path(base_dir)

    def get_prompt_path(self, prompt_name: str) -> Path:
        """Get full path to a prompt file."""
        return self.prompts_base_dir / prompt_name

    def reload(self):
        """Reload configuration from file."""
        self._load_config()


# Singleton instance
_default_config: Optional[Config] = None


def get_config(env: str = 'dev', language: str = 'cn') -> Config:
    """Get configuration instance with language support."""
    global _default_config
    if _default_config is None:
        _default_config = Config(env)
    _default_config.set_language(language)
    return _default_config
