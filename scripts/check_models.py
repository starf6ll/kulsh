#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal live check of EtageOne models (1-2 tokens each).

Usage (Windows):
    $env:ETAGEONE_API_KEY="sk-..."; python scripts/check_models.py
Usage (Linux/macOS):
    ETAGEONE_API_KEY=sk-... python scripts/check_models.py
"""
from __future__ import annotations

import asyncio
import os
import sys

import aiohttp

URL = "https://api.etage.one/v1/chat/completions"
MODELS = [
    "glm-5.3-flash",
    "deepseek-v4.1-flash",
    "kimi-k3",
    "deepseek-v4-pro",
    "gpt-6-luna",
    "claude-haiku-5-5",
    "gpt-6.1-sol",
    "gpt-6-astra",
    "grok-4.7",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "qwen3.8-max-0902",
]


async def check(session: aiohttp.ClientSession, key: str, model: str) -> tuple[str, bool, str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 2,
    }
    try:
        async with session.post(URL, json=payload, headers={"Authorization": f"Bearer {key}"},
                                timeout=aiohttp.ClientTimeout(total=40)) as resp:
            body = (await resp.text())[:160]
            return model, resp.status == 200, f"{resp.status} {body}"
    except Exception as e:
        return model, False, f"{type(e).__name__}: {e}"


async def main() -> None:
    key = os.getenv("ETAGEONE_API_KEY") or ""
    if not key:
        print("ETAGEONE_API_KEY is not set")
        sys.exit(2)
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*(check(session, key, m) for m in MODELS))
    ok = 0
    for model, good, info in results:
        print(("OK   " if good else "FAIL ") + model + "  " + info)
        ok += int(good)
    print(f"\n{ok}/{len(results)} models responded")


if __name__ == "__main__":
    asyncio.run(main())
