#!/usr/bin/env python3
"""列出 LiteLLM 网关当前可用的模型（请求 /v1/models）。"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import get_config

try:
    import httpx
except ImportError:
    print("请安装: pip install httpx")
    sys.exit(1)


def main():
    config = get_config()
    base_url = config.gateway_base_url
    api_key = config.gateway_api_key

    if not base_url:
        print("未配置 LITELLM_PROXY_API_BASE。")
        sys.exit(1)

    url = f"{base_url}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    print(f"请求: {url}")
    try:
        r = httpx.get(url, headers=headers, timeout=30.0)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        print(f"HTTP 错误: {e.response.status_code}")
        print(e.response.text[:500])
        sys.exit(1)
    except Exception as e:
        print(f"请求失败: {e}")
        sys.exit(1)

    models = data.get("data") if isinstance(data.get("data"), list) else []
    if not models:
        print("未返回模型列表，原始 JSON：")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
        return

    ids = sorted((m.get("id") or m.get("model") or "(无 id)") for m in models)
    print(f"\n共 {len(ids)} 个模型：\n")
    for mid in ids:
        print(f"  - {mid}")
    print()


if __name__ == "__main__":
    main()
