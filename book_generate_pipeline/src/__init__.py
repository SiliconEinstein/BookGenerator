"""Topic Book Generator - Source Package.

在导入任何子模块前统一加载项目根目录的 .env，避免各模块各自 load_dotenv
造成的加载顺序依赖。
"""

from pathlib import Path

try:
    import dotenv
except ImportError:  # dotenv 可选，缺失时只依赖真实环境变量
    pass
else:
    _dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if _dotenv_path.exists():
        dotenv.load_dotenv(dotenv_path=_dotenv_path, override=False)
