from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from verbatim.analytics.latency import summarize_call_events
from verbatim.events import load_events


def _fmt(value: Any, suffix: str = " ms") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        value = round(value)
    return f"{value}{suffix}"


def format_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"Call: {summary.get('call_id') or 'all'}",
        f"Turns: {summary['total_turns']}",
        f"Successful turns: {summary['successful_turns']}",
        f"Failed turns: {summary['failed_turns']}",
        f"Interrupted turns: {summary['interrupted_turns']}",
        f"LLM provider: {summary.get('llm_provider') or 'n/a'}",
        f"LLM model: {summary.get('llm_model') or 'n/a'}",
        "",
        "Perceived response latency:",
        f"  avg: {_fmt(summary['avg_perceived_latency_ms'])}",
        f"  p50: {_fmt(summary['p50_perceived_latency_ms'])}",
        f"  p90: {_fmt(summary['p90_perceived_latency_ms'])}",
        f"  p95: {_fmt(summary['p95_perceived_latency_ms'])}",
        f"  max: {_fmt(summary['max_perceived_latency_ms'])}",
        "",
        "Transcript-ready to playback latency:",
        f"  avg: {_fmt(summary.get('avg_transcript_ready_to_playback_ms'))}",
        f"  p50: {_fmt(summary.get('p50_transcript_ready_to_playback_ms'))}",
        f"  p90: {_fmt(summary.get('p90_transcript_ready_to_playback_ms'))}",
        f"  p95: {_fmt(summary.get('p95_transcript_ready_to_playback_ms'))}",
        f"  max: {_fmt(summary.get('max_transcript_ready_to_playback_ms'))}",
        "",
        "Breakdown averages:",
        f"  turn detection: {_fmt(summary['avg_turn_detection_latency_ms'])}",
        f"  STT final: {_fmt(summary['avg_stt_final_latency_ms'])}",
        f"  STT eager EOT: {_fmt(summary.get('avg_stt_eager_eot_latency_ms'))}",
        f"  STT final EOT: {_fmt(summary.get('avg_stt_final_eot_latency_ms'))}",
        f"  eager-to-final gap: {_fmt(summary.get('avg_eager_to_final_gap_ms'))}",
        f"  transcript to LLM enqueue: {_fmt(summary.get('avg_transcript_to_llm_enqueue_ms'))}",
        f"  transcript ready to LLM enqueue: {_fmt(summary.get('avg_transcript_ready_to_llm_enqueue_ms'))}",
        f"  LLM queue: {_fmt(summary.get('avg_llm_queue_latency_ms'))}",
        f"  LLM provider first chunk: {_fmt(summary.get('avg_llm_provider_first_chunk_ms'))}",
        f"  LLM provider TTFB: {_fmt(summary.get('avg_llm_provider_ttfb_ms'))}",
        f"  LLM provider TTFB p95: {_fmt(summary.get('p95_llm_provider_ttfb_ms'))}",
        f"  first token to 3 words: {_fmt(summary.get('avg_first_token_to_3_words_ms'))}",
        f"  first token to 6 words: {_fmt(summary.get('avg_first_token_to_6_words_ms'))}",
        f"  first token to speakable phrase: {_fmt(summary.get('avg_first_token_to_speakable_phrase_ms'))}",
        f"  max inter-token gap: {_fmt(summary.get('avg_max_inter_token_gap_ms'))}",
        f"  first token to text frame: {_fmt(summary.get('avg_first_token_to_text_frame_ms'))}",
        f"  text frame to TTS input: {_fmt(summary.get('avg_text_frame_to_tts_input_ms'))}",
        f"  speakable phrase to TTS input: {_fmt(summary.get('avg_first_speakable_phrase_to_tts_input_ms'))}",
        f"  speakable phrase to audio: {_fmt(summary.get('avg_speakable_phrase_to_tts_audio_ms'))}",
        f"  LLM total TTFT: {_fmt(summary.get('avg_llm_ttft_total_ms'))}",
        f"  first text to TTS: {_fmt(summary.get('avg_llm_first_text_to_tts_ms'))}",
        f"  TTS TTFB: {_fmt(summary['avg_tts_ttfb_ms'])}",
        f"  playback start delay: {_fmt(summary['avg_playback_latency_ms'])}",
        f"  LLM started on: {summary.get('llm_started_on_counts') or {}}",
        f"  turn resumed count: {summary.get('turn_resumed_count', 0)}",
        f"  eager cancel count: {summary.get('eager_cancel_count', 0)}",
        f"  active LLM cancelled: {summary.get('active_llm_cancelled_count', 0)}",
        f"  barge-in before audio: {summary.get('barge_in_before_audio_count', 0)}",
        f"  stale LLM completed: {summary.get('stale_llm_completed_count', 0)}",
        f"  phantom turns prevented: {summary.get('phantom_turn_prevented_count', 0)}",
        f"  echo frames suppressed: {summary.get('echo_suppressed_count', 0)}",
        f"  clean p95: {_fmt(summary.get('clean_p95_transcript_ready_to_playback_ms'))}",
        f"  interrupted p95: {_fmt(summary.get('interrupted_p95_transcript_ready_to_playback_ms'))}",
        f"  first-turn p95: {_fmt(summary.get('first_turn_p95_transcript_ready_to_playback_ms'))}",
        f"  later-turn p95: {_fmt(summary.get('later_turn_p95_transcript_ready_to_playback_ms'))}",
        "",
        "P95 bottleneck contributors:",
    ]
    contributors = summary.get("p95_bottleneck_contributors") or []
    if contributors:
        for item in contributors:
            lines.append(
                f"  {item.get('bottleneck')}: {item.get('percent')}% ({item.get('turns')} turns)"
            )
    else:
        lines.append("  none")

    lines.extend([
        "",
        "Provider errors:",
    ])
    errors = summary.get("error_count_by_provider") or {}
    if errors:
        for provider, count in sorted(errors.items()):
            lines.append(f"  {provider}: {count}")
    else:
        lines.append("  none: 0")

    slow_turns = [
        turn
        for turn in summary.get("turns", [])
        if _turn_display_latency(turn) is not None
        and _turn_display_latency(turn) > 2000
    ]
    if slow_turns:
        lines.extend(["", "Turns above 2000 ms:"])
        for turn in slow_turns:
            latency = _turn_display_latency(turn)
            perceived = (turn.get("latency") or {}).get("perceived_response_latency_ms")
            lines.append(
                f"  {turn['turn_id']}: real {_fmt(latency)} / perceived {_fmt(perceived)}"
                f" (bottleneck: {turn.get('dominant_bottleneck') or 'unknown'}, "
                f"slowest stage: {turn.get('slowest_stage') or 'unknown'})"
            )
    return "\n".join(lines)


def _turn_display_latency(turn: dict[str, Any]) -> float | None:
    latency = turn.get("latency") or {}
    return latency.get("transcript_ready_to_playback_ms") or latency.get(
        "perceived_response_latency_ms"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Verbatim JSONL latency events.")
    parser.add_argument("--events", default="./data/verbatim/events.jsonl", help="Path to events JSONL.")
    parser.add_argument("--call-id", default=None, help="Optional call id filter.")
    args = parser.parse_args(argv)

    events_path = Path(args.events)
    events = load_events(events_path)
    summary = summarize_call_events(events, call_id=args.call_id)
    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
