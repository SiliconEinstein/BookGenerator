from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from app.config import PDF_HOST, PDF_PARSER_SCRIPT

def parse_pdf_source(source_type: str, source_file_url: str, output_dir: Path) -> dict:
    args = ['python3', str(PDF_PARSER_SCRIPT), '--formats', 'plain', '--host', PDF_HOST, '--output-dir', str(output_dir)]
    if source_type == 'url':
        args.extend(['--url', source_file_url])
    else:
        args.extend(['--file', source_file_url])
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout.strip())
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        if source_type != 'file':
            raise
        payload = _parse_pdf_local(source_file_url, output_dir)
    parser_file = next((item for item in payload.get('formatted_files', []) if item.endswith('.plain')), None)
    if not parser_file:
        parser_file = payload.get('parser_file')
    return {'token': payload.get('token'), 'result_json': payload.get('result_json'), 'parser_file': parser_file}


def _parse_pdf_local(source_file_url: str, output_dir: Path) -> dict:
    from pypdf import PdfReader

    output_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(source_file_url)
    text = '\n'.join((page.extract_text() or '') for page in reader.pages)
    token = re.sub(r'[^-._?=&a-zA-Z0-9]', '', Path(source_file_url).stem)[:128] or 'localpdf'
    plain_path = output_dir / f'{token}-parser.plain'
    plain_path.write_text(text, encoding='utf-8')
    return {'token': token, 'result_json': None, 'formatted_files': [str(plain_path)], 'parser_file': str(plain_path)}
