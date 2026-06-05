from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / 'prompts'


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f'{name}.md'
    if not path.exists():
        raise FileNotFoundError(f'Prompt not found: {path}')
    return path.read_text(encoding='utf-8').strip()


def render_prompt(name: str, **kwargs: str) -> str:
    template = load_prompt(name)
    return template.format(**kwargs)
