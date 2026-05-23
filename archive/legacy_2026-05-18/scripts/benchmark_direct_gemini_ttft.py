#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Iterable

from verbatim.config import DEFAULT_SYSTEM_PROMPT, clear_settings_cache, get_settings, load_env_file


def percentile(values: Iterable[float], p: int) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, round((p / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)


def sample_gemini_ttft(*, model: str, prompt: str, system_prompt: str, max_tokens: int) -> dict:
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.providers.google_api_key:
        raise SystemExit("GOOGLE_API_KEY is required for direct Gemini TTFT benchmark.")

    client = genai.Client(api_key=settings.providers.google_api_key)
    start = time.perf_counter()
    first_chunk_ms: float | None = None
    chars = 0
    chunks = 0
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=max_tokens,
        temperature=0.2,
    )
    stream = client.models.generate_content_stream(
        model=model,
        contents=prompt,
        config=config,
    )
    for chunk in stream:
        text = getattr(chunk, "text", None) or ""
        if text and first_chunk_ms is None:
            first_chunk_ms = round((time.perf_counter() - start) * 1000, 3)
        if text:
            chunks += 1
            chars += len(text)
    total_ms = round((time.perf_counter() - start) * 1000, 3)
    return {
        "provider": "gemini",
        "model": model,
        "first_chunk_ms": first_chunk_ms,
        "total_ms": total_ms,
        "chunks": chunks,
        "characters": chars,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure Gemini streaming TTFT outside Pipecat/Daily/Cartesia."
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--prompt",
        default="Say yes in one short natural sentence.",
    )
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Print raw sample JSON.")
    args = parser.parse_args()

    load_env_file()
    clear_settings_cache()
    settings = get_settings()
    model = args.model or settings.providers.gemini_model
    max_tokens = args.max_tokens or settings.prompt.max_tokens

    samples = [
        sample_gemini_ttft(
            model=model,
            prompt=args.prompt,
            system_prompt=args.system_prompt,
            max_tokens=max_tokens,
        )
        for _ in range(args.samples)
    ]
    first_chunks = [
        sample["first_chunk_ms"] for sample in samples if sample["first_chunk_ms"] is not None
    ]
    totals = [sample["total_ms"] for sample in samples]
    summary = {
        "provider": "gemini",
        "model": model,
        "samples": len(samples),
        "system_prompt_chars": len(args.system_prompt),
        "max_tokens": max_tokens,
        "first_chunk_avg_ms": round(statistics.mean(first_chunks), 3) if first_chunks else None,
        "first_chunk_p50_ms": percentile(first_chunks, 50),
        "first_chunk_p90_ms": percentile(first_chunks, 90),
        "first_chunk_p95_ms": percentile(first_chunks, 95),
        "first_chunk_max_ms": round(max(first_chunks), 3) if first_chunks else None,
        "total_avg_ms": round(statistics.mean(totals), 3) if totals else None,
        "total_p95_ms": percentile(totals, 95),
    }

    if args.json:
        print(json.dumps({"summary": summary, "samples": samples}, indent=2))
        return

    print("Direct Gemini streaming TTFT")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
