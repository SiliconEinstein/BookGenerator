from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = Path(os.getenv('OUTPUT_ROOT', BASE_DIR / 'data/outputs'))
PDF_PARSER_SCRIPT = Path(os.getenv('PDF_PARSER_SCRIPT', BASE_DIR / 'tools/pdf_parser/pdf_parser.py'))
PDF_HOST = os.getenv('PDF_HOST', 'http://101.126.82.63:40001')
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '3200'))
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '')
CALLBACK_AUTH_TOKEN = os.getenv('CALLBACK_AUTH_TOKEN', '')
GPUGEEK_API_KEY = os.getenv('GPUGEEK_API_KEY', '00u14bi9fo1k9h01000deu6szt7f07n5009w6vsv')
GPUGEEK_API_BASE = os.getenv('GPUGEEK_API_BASE', 'https://api.gpugeek.com/v1')
BACKEND_BASE_URL = os.getenv('BACKEND_BASE_URL', 'https://bohrium-core.test.dp.tech')
BACKEND_AUTH_TOKEN = os.getenv('BACKEND_AUTH_TOKEN', '')
OSS_TOKEN_PATH = os.getenv('OSS_TOKEN_PATH', '/api/v1/courses/ai/common/token')
OSS_UPLOAD_URL = os.getenv('OSS_UPLOAD_URL', 'https://tiefblue.test.dp.tech/api/upload/binary')
