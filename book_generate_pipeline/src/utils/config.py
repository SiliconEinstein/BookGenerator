"""Configuration management for the project."""

import os
import re
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path

# 角色 -> 覆盖用的环境变量名
_MODEL_ENV_OVERRIDES = {
    "writer": "LLM_WRITER_MODEL",
    "reviewer": "LLM_REVIEWER_MODEL",
    "utility": "LLM_UTILITY_MODEL",
    "vision": "LLM_VISION_MODEL",
    "image": "LLM_IMAGE_MODEL",
}


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

    def _interpolate_env(self, data: Any) -> Any:
        """Replace ${VAR} tokens with environment values."""
        if isinstance(data, dict):
            return {key: self._interpolate_env(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self._interpolate_env(value) for value in data]
        if isinstance(data, str):
            def _replace(match: re.Match) -> str:
                return os.environ.get(match.group(1), "")
            return re.sub(r"\$\{([^}]+)\}", _replace, data)
        return data

    def _load_config(self):
        """Load configuration from YAML file."""
        config_file = Path(__file__).parent.parent.parent / 'config' / f'config.{self.env}.yaml'
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_file}")
        with open(config_file, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f) or {}
        self._config_cache = self._interpolate_env(raw_config)

    # ---- LLM ----

    @property
    def _llm(self) -> Dict[str, Any]:
        return self._config_cache.get('llm', {})

    @property
    def gateway_base_url(self) -> str:
        """LiteLLM 网关地址（不带尾部斜杠）。"""
        return str(self._llm.get('gateway', {}).get('base_url', '')).rstrip('/')

    @property
    def gateway_api_key(self) -> str:
        return str(self._llm.get('gateway', {}).get('api_key', ''))

    def get_model(self, role: str) -> str:
        """按角色取模型名，环境变量优先于 YAML。"""
        env_key = _MODEL_ENV_OVERRIDES.get(role)
        if env_key:
            override = os.environ.get(env_key, "").strip()
            if override:
                return override
        model = self._llm.get('models', {}).get(role)
        if not model:
            raise KeyError(f"未配置模型角色 '{role}'，请检查 config/config.{self.env}.yaml")
        return str(model)

    @property
    def evaluator_models(self) -> List[str]:
        """大纲 battle 的评委模型列表。"""
        models = self._llm.get('evaluators') or []
        return [str(m) for m in models if m]

    @property
    def writer_fallback_models(self) -> List[str]:
        """writer 调用失败后的降级模型列表。"""
        models = self._llm.get('writer_fallbacks') or []
        return [str(m) for m in models if m]

    # ---- 其他服务 ----

    @property
    def wiki_search_api_base(self) -> str:
        """Get wiki search API base URL."""
        return str(self._config_cache.get('wiki', {}).get('search_api_base', '')).rstrip('/')

    @property
    def output_base_dir(self) -> Path:
        """Get base output directory."""
        return Path(self._config_cache.get('output', {}).get('base_dir', 'output/books'))

    @property
    def output_temp_dir(self) -> Path:
        """Get temp output directory."""
        return Path(self._config_cache.get('output', {}).get('temp_dir', 'output/temp'))

    # ---- Prompts ----

    @property
    def prompts_base_dir(self) -> Path:
        """Get prompts base directory based on language setting."""
        prompts_config = self._config_cache.get('prompts', {})
        base_dir = (
            prompts_config.get('base_dir_en', 'prompts_en') if self.language == 'en'
            else prompts_config.get('base_dir_ch', 'prompts')
        )
        return Path(base_dir)

    def get_prompt_path(self, prompt_name: str) -> Path:
        """Get full path to a prompt file."""
        return self.prompts_base_dir / prompt_name

    def get_prompt_name(self, key: str, default: Optional[str] = None) -> str:
        """Get prompt filename by logical key."""
        names = self._config_cache.get('prompts', {}).get('names', {})
        return names.get(key, default or key)

    def reload(self):
        """Reload configuration from file."""
        self._load_config()


# Singleton instance
_default_config: Optional[Config] = None


def get_config(env: str = 'dev', language: str = 'ch') -> Config:
    """Get configuration instance with language support."""
    global _default_config
    if _default_config is None:
        _default_config = Config(env)
    _default_config.set_language(language)
    return _default_config
