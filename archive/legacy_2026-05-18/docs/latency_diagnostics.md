# Latency Diagnostics

Run each benchmark with a fresh call so summaries do not mix providers or modes.

## Baseline

- STT: Nova-3 (`deepgram`, `nova-3-general`)
- LLM: Gemini 2.5 Flash (`gemini-2.5-flash`)
- TTS: Cartesia sentence aggregation
- Prompt: `Answer briefly in one natural spoken sentence.`
- History: 2 messages
- Max output: 32 tokens
- LLM temperature: 0
- Turn stop safety timeout: 5.0 seconds
- Deepgram endpointing: 100 ms
- Deepgram utterance end: 1000 ms
- Echo suppression: off (`0` ms)

Deepgram's public streaming `utterance_end_ms` minimum is 1000 ms, so keep low-latency
turn detection focused on endpointing and Pipecat's user turn timeout.
The baseline uses Pipecat's documented default turn strategy stack: Silero VAD and
transcription for turn start, and local Smart Turn for turn end. `user_turn_stop_timeout`
is kept as Pipecat's safety net rather than an aggressive end-of-turn knob.

## A. Mock LLM Full Pipeline

In the UI, select `Mock`, then run 30 turns. This measures Daily + Deepgram + Cartesia
without live LLM provider latency.

Expected latency floor is roughly:

```text
turn_detection + tts_first_audio + playback_overhead
```

## B. Direct Gemini TTFT

Run Gemini streaming outside Pipecat, Daily, and Cartesia:

```bash
uv run python scripts/benchmark_direct_gemini_ttft.py --samples 30
```

If direct Gemini first-chunk p50 is above about 700 ms, classify Gemini/provider/network
as the blocking layer for the 700 ms target.

## C. Mock STT Input

Use the UI with a stable room and compare the direct Gemini benchmark against the full
pipeline. If direct Gemini is fast but full pipeline `provider_ttft` is slow, inspect
Pipecat orchestration, context aggregation, and network contention.

## D. Mock TTS

Use the call summary fields `avg_llm_provider_ttfb_ms`, `avg_llm_ttft_total_ms`,
`avg_text_frame_to_tts_input_ms`, and `avg_tts_ttfb_ms` to determine whether TTS is
material to the slow turn. If LLM timing alone exceeds the target, do not tune Cartesia
first.

## What To Watch

- `llm_provider_ttfb_ms`: provider/network time to first streamed chunk.
- `first_token_to_text_frame_ms`: Pipecat time from raw provider token to text frame.
- `text_frame_to_tts_input_ms`: pipeline handoff from LLM output to TTS input.
- `active_llm_cancelled_count`: stale LLM requests cancelled on barge-in.
- `stale_llm_completed_count`: cancelled LLMs that still completed later.
- `phantom_turn_prevented_count`: assistant/output frames blocked from creating fake turns.
- `echo_suppressed_count`: likely speaker-to-mic echo frames observed while the assistant
  was speaking or during the short cooldown after assistant audio. These are diagnostic
  markers only when echo suppression is left at `0`.
- `clean_p95_ms` and `real_p95_ms`: clean turns exclude interruptions, tool calls, stale
  LLM completions, and errors; real p95 includes the messy demo path.
- `valid_barge_in_count` / `false_barge_in_count`: whether tiered interruption policy
  upgraded user speech to a real interruption or treated it as uncertain noise.
- `premature_assistant_start_count`: user resumed quickly after playback started, suggesting
  Alicia may have answered before the user finished.
- `user_utterance_split_count`: two committed user turns looked like one continuous thought.
- `voice_cutout_suspected_count`: assistant speech was cancelled while audio was active.
- `form_pattern_failure_count`: Alicia generated a form-like question or recap pattern.
- `conversation_mode_counts`: deterministic mode controller distribution for Alicia turns.

## Demo Benchmark Shape

For the current WebRTC demo target, use a 30-turn run:

```text
10 short functional turns
10 natural Dubai real-estate inquiry turns
5 long-sentence turns
5 interruption/recovery turns
```

Pass target:

```text
real_p95_ms < 900
clean_p95_ms < 700
voice_cutout_suspected_count = 0
premature_assistant_start_count <= 1
user_utterance_split_count <= 1
form_pattern_failure_count <= 1
```
