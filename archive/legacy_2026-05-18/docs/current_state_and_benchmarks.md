# Verbatim Current State And Benchmarks

Last updated: 2026-05-15

This document captures where the Verbatim voice-agent prototype is now, what stack is currently winning, which benchmarks have been reached, why the system evolved this way, and what remains unresolved.

No API keys or provider secrets are included here.

## Executive Summary

Verbatim began as a greenfield Pipecat WebRTC voice pipeline:

```text
Daily -> Deepgram STT -> Gemini LLM -> Cartesia TTS -> Daily audio output
```

The current best cascade stack is now:

```text
LiveKit -> Deepgram Nova-3 -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3 -> LiveKit audio output
```

The current experimental audio-native stack is:

```text
LiveKit -> UltraVox Realtime -> LiveKit audio output
```

The main milestone achieved is that LiveKit + Nova-3 + Groq + Cartesia can reach a conversational-feeling latency band around 400-700 ms in good runs, with occasional spikes around 1000-1500 ms. This is a major improvement over the earlier 2000-5000 ms average runs.

The main remaining issues are not basic plumbing anymore. They are:

1. Interruption behavior: the system can still cut the user off or treat a long sentence as multiple turns.
2. Assistant voice cutouts: audio can still interrupt or drop while the agent is speaking.
3. p95 reliability: average latency is strong, but tails are still inconsistent.
4. Conversation intelligence: fast models often slip into a form-like real estate questionnaire pattern.
5. Telemetry accuracy: p95 and perceived latency are clearer than before, but some historical call files were generated before the latest fallback/source labeling changes.

## Current Recommended Stack

Use this as the main testing baseline unless explicitly testing another branch:

```text
Transport: LiveKit
STT: Deepgram Nova-3, nova-3-general
LLM: Groq, llama-3.1-8b-instant
TTS: Cartesia, sonic-3
Mode: Aggressive latency diagnostic
Prompt: Alicia, CRTG Real Estate Dubai concierge
```

Current safe configuration snapshot from the local app:

```text
VERBATIM_TRANSPORT_PROVIDER=livekit
VERBATIM_STT_PROVIDER=deepgram
VERBATIM_DEEPGRAM_MODEL=nova-3-general
VERBATIM_DEEPGRAM_ENDPOINTING=100
VERBATIM_DEEPGRAM_UTTERANCE_END_MS=1000
VERBATIM_LLM_PROVIDER=groq
VERBATIM_GROQ_MODEL=llama-3.1-8b-instant
VERBATIM_LLM_MAX_TOKENS=32
VERBATIM_LLM_HISTORY_MESSAGES=1
VERBATIM_LLM_TEMPERATURE=0
VERBATIM_CARTESIA_MODEL=sonic-3
VERBATIM_TTS_TEXT_AGGREGATION_MODE=sentence
VERBATIM_LATENCY_DIAGNOSTIC_MODE=true
VERBATIM_FINAL_TRANSCRIPT_EAGER_COMMIT=true
VERBATIM_FINAL_TRANSCRIPT_COMMIT_DELAY_MS=0
VERBATIM_FINAL_TRANSCRIPT_FRAGMENT_DELAY_MS=220
VERBATIM_VAD_ONLY_USER_TURN_START=true
VERBATIM_USER_TURN_STOP_TIMEOUT=5.0
VERBATIM_LLM_PREWARM=true
```

Current LiveKit audio settings:

```text
VERBATIM_LIVEKIT_AUDIO_OUT_10MS_CHUNKS=4
VERBATIM_LIVEKIT_AUDIO_OUT_BITRATE=96000
VERBATIM_LIVEKIT_AUDIO_OUT_AUTO_SILENCE=true
VERBATIM_LIVEKIT_BROWSER_ECHO_CANCELLATION=true
VERBATIM_LIVEKIT_BROWSER_NOISE_SUPPRESSION=true
VERBATIM_LIVEKIT_BROWSER_AUTO_GAIN_CONTROL=true
VERBATIM_LIVEKIT_BROWSER_AUDIO_SAMPLE_RATE=48000
```

Current tiered barge-in and quality-metric settings:

```text
VERBATIM_ASSISTANT_MIN_SPEAK_MS_BEFORE_BARGE_IN=400
VERBATIM_BARGE_IN_MIN_SPEECH_MS=300
VERBATIM_BARGE_IN_MIN_TRANSCRIPT_WORDS=2
VERBATIM_HARD_INTERRUPT_PHRASES="stop,wait,hold on,let me finish,actually,no"
VERBATIM_UTTERANCE_SPLIT_WINDOW_MS=1200
VERBATIM_USER_RESUME_AFTER_ASSISTANT_WINDOW_MS=800
```

Current UltraVox experiment settings:

```text
VERBATIM_ULTRAVOX_MODEL=fixie-ai/ultravox
VERBATIM_ULTRAVOX_TURN_ENDPOINT_DELAY_SECONDS=0.256
VERBATIM_ULTRAVOX_MINIMUM_TURN_DURATION_SECONDS=0.064
VERBATIM_ULTRAVOX_MINIMUM_INTERRUPTION_DURATION_SECONDS=0.36
VERBATIM_ULTRAVOX_FRAME_ACTIVATION_THRESHOLD=0.2
VERBATIM_ULTRAVOX_CLIENT_BUFFER_SIZE_MS=80
```

## Why The Stack Became This

### Daily To LiveKit

Daily was the initial WebRTC transport because it was simple to set up and worked well for a minimal browser room. It exposed the first round of problems quickly:

- Joining required camera/microphone permission and a display name.
- Multiple bot instances could keep running after browser leave events.
- The Daily path was usable, but latency and room lifecycle debugging were harder than expected.
- The same Deepgram/LLM/Cartesia stack felt more reliable after adding LiveKit.

LiveKit was added side by side, not as a replacement. The UI can still select Daily or LiveKit. LiveKit became the main benchmark path because the same cascade stack produced lower and more consistent observed latency.

### Flux Back To Nova-3

Deepgram Flux eager end-of-turn was tested because it should, in theory, let the LLM start earlier. In practice, it underperformed in this app:

- Flux perceived latency was significantly worse than Nova in observed tests.
- Most LLM starts were still final-transcript based, so eager EOT was not delivering enough practical benefit.
- Flux eager/final EOT metrics were initially calculated against the wrong baseline and produced unrealistic values.
- Nova-3 produced much better turn detection in the current setup.

Decision:

```text
Production/control STT: Deepgram Nova-3
Experimental STT: Deepgram Flux
```

Flux should stay experimental until it beats Nova on p50, p95, and interruption behavior with correct eager-EOT telemetry.

### Gemini To Groq

Gemini 2.5 Flash was the initial low-latency baseline. It was useful for diagnostics and usually more capable than tiny models, but it repeatedly showed first-token latency that was too high for the 500-700 ms target.

Groq LLaMA 3.1 8B Instant became the practical latency baseline because provider TTFT often landed around 90-180 ms in good runs. The tradeoff is model intelligence and style. The agent can become repetitive, literal, or form-like unless the prompt and response guard are strict.

Decision:

```text
Latency baseline: Groq LLaMA 3.1 8B Instant
Quality/diagnostic comparison: Gemini 2.5 Flash
Other providers: available but not current winners
```

### Cartesia Stayed

Cartesia has remained in the cascade since the beginning because its voice quality is strong and its TTS first-audio time is usually not the primary bottleneck. In good LiveKit/Groq runs, Cartesia TTFB is usually in the 140-280 ms band, with occasional spikes.

The voice cutout problem is still open, but the evidence so far does not show Cartesia as the only cause. LiveKit buffering, interruption handling, barge-in policy, and output chunking also matter.

Decision:

```text
Keep Cartesia as the main TTS for the cascade path.
Tune output stability before replacing it.
```

### Why UltraVox Was Added

UltraVox was added to test whether an audio-native model could remove the whole STT -> text LLM -> TTS cascade and therefore reduce latency, improve interruptions, and possibly sound more natural.

UltraVox currently works as a LiveKit-only experiment:

```text
LiveKit -> UltraVox Realtime -> LiveKit
```

It can show very low transcript-to-playback latency, but it has its own problems:

- Interruption counts are high in recent runs.
- Perceived latency needs fallback metrics because UltraVox does not always emit the same user-speech-stop timestamps as the cascade.
- Prompt control is harder because the normal text response guard cannot rewrite audio that UltraVox has already generated.
- There have been audio interruptions/cutouts during speech.

Decision:

```text
Keep UltraVox as a serious experiment, but not the current default.
```

## Benchmarks Reached

The following table uses current analytics recomputation from `data/verbatim/events.jsonl` where available. Older call summary JSON files may not include the newer `perceived_latency_source` field, so treat this table as more reliable than old static summaries.

### Current Best Cascade Runs

| Call ID | Stack | Turns | Avg perceived | p95 perceived | Source | Avg transcript to playback | Avg provider TTFT | Avg TTS TTFB | Notes |
|---|---:|---:|---:|---:|---|---:|---:|---:|---|
| `call_16c88648aba3` | LiveKit + Nova-3 + Groq + Cartesia | 22 | 221 ms | 368 ms | user speech stopped | 592 ms | 129 ms | 142 ms | Best recorded cascade run, likely optimistic on perceived timing |
| `call_051093198ed0` | LiveKit + Nova-3 + Groq + Cartesia | 27 | 342 ms | 1452 ms | user speech stopped | 421 ms | 113 ms | 243 ms | Strong real benchmark, one interruption |
| `call_aee67c9b1807` | LiveKit + Nova-3 + Groq + Cartesia | 22 | 518 ms | 1497 ms | user speech stopped | 591 ms | 184 ms | 278 ms | Matches the felt 400-700 ms improvement band |
| `call_05db6f37e982` | LiveKit + Nova-3 + Groq + Cartesia | 30 | 558 ms | 841 ms | user speech stopped | 721 ms | 271 ms | 148 ms | Good p95 but high interruption count in that run |
| `call_fa4ad7f1f7fc` | LiveKit + Nova-3 + Groq + Cartesia | 20 | 577 ms | 2228 ms | user speech stopped | 647 ms | 130 ms | 252 ms | Good average, p95 still too high |

Practical benchmark reached:

```text
Good runs: 400-700 ms felt latency
Good p95 runs: around 840-1500 ms
Bad p95 runs: above 2000 ms still possible
```

The project has reached the first useful interaction band, but not yet the final reliability target.

### UltraVox Realtime Runs

| Call ID | Stack | Turns | Avg displayed perceived | p95 displayed perceived | Source | Avg provider TTFT | Interruption turns | Notes |
|---|---:|---:|---:|---:|---|---:|---:|---|
| `call_541420441d35` | LiveKit + UltraVox | 29 | 230 ms | 664 ms | transcript ready to playback | 36 ms | 14 | Very low measured response path, but too interruption-heavy |
| `call_597c0cd749b8` | LiveKit + UltraVox | 13 | 252 ms | 748 ms | transcript ready to playback | 3 ms | 6 | Latest inspected call had bad conversation pattern and interruption issues |
| `call_a7f641cccd59` | LiveKit + UltraVox | 25 | 296 ms | 386 ms | transcript ready to playback | 0.3 ms | 11 | Fast, but interruption-heavy |

UltraVox has promising latency, but the interaction quality and interruption stability are not yet better than the cascade.

### Other LLM Provider Comparisons

| Call ID | Stack | Turns | Avg perceived | p95 perceived | Avg provider TTFT | Avg TTS TTFB | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| `call_edb2d6ee936b` | LiveKit + Nova-3 + Gemini + Cartesia | 8 | 1265 ms | 1690 ms | 616 ms | 501 ms | Usable but slower than Groq |
| `call_f7b9bcdaa752` | LiveKit + Nova-3 + OpenAI GPT-4o mini + Cartesia | 3 | 1372 ms | 1372 ms | 1775 ms | 136 ms | Too small a sample, provider TTFT high |
| `call_f11a63715596` | LiveKit + Nova-3 + Qwen + Cartesia | 4 | 13873 ms | 13873 ms | 13150 ms | 147 ms | Not viable in this test |
| `call_807d1513a40a` | LiveKit + Nova-3 + xAI Grok + Cartesia | 5 | 1178 ms | 2219 ms | 878 ms | 139 ms | Better than Qwen, slower than Groq |
| `call_67efb52320f9` | LiveKit + Nova-3 + xAI Grok + Cartesia | 8 | 2177 ms | 3958 ms | 1178 ms | 145 ms | Tail too high |

Current conclusion:

```text
Groq LLaMA 3.1 8B Instant is the fastest usable cascade LLM in the local benchmark data.
Gemini is more comfortable as a diagnostic/quality comparison than the latency baseline.
Qwen was not viable in the observed run.
xAI Grok Fast was not yet stable or fast enough in this setup.
```

### Earlier Reported Milestones

These were reported during interactive testing before all telemetry fixes landed:

| Phase | Observed result | Outcome |
|---|---:|---|
| Initial Daily/Nova/Gemini style path | Around 2000-5000 ms perceived in many runs | Too slow |
| Nova-3 vs Flux comparison | Nova around 1025-1473 ms average, Flux often 2500-4700 ms average | Nova won |
| LiveKit introduction | Around 722 ms avg, p95 around 813 ms in an early 5-turn test | LiveKit looked much better |
| LiveKit + Nova-3 + Groq | Often 400-700 ms felt latency | Became main stack |
| UltraVox experiment | 230-300 ms transcript-to-playback, but high interruptions | Promising but unstable |

## What Is Implemented

### App And UI

The app is a single Python/FastAPI service with a local browser dashboard.

Current public server routes:

```text
GET  /
GET  /api/health
GET  /api/config
POST /api/rooms
POST /api/agent/start
POST /api/agent/stop
GET  /api/agent/status
GET  /api/analytics/summary
GET  /api/analytics/transcript
```

The browser UI supports:

- Daily vs LiveKit transport selection.
- Nova-3 vs Flux STT selection.
- Gemini, Groq, OpenAI, Qwen, xAI, UltraVox, and Mock LLM selection.
- Agent start/stop, including a kill button for the current agent.
- Live terminal view for bot/session events.
- Transcript display.
- Right-side latency panel with current call, model, perceived latency, p95, transcript-to-playback, transcript-to-enqueue, turn detection, LLM TTFT, provider TTFT, and TTS first audio.

### Pipeline Paths

Cascade path:

```text
transport.input()
-> instrumentation
-> Deepgram STT
-> STT instrumentation
-> optional Flux eager LLM processor
-> final transcript eager LLM processor
-> Pipecat user aggregator
-> final context gate
-> LLM queue instrumentation
-> context limiter
-> pre-LLM instrumentation
-> selected text LLM
-> LLM error recovery
-> LLM event instrumentation
-> Alicia response style guard
-> optional fast-ack processor
-> Cartesia TTS
-> TTS instrumentation
-> transport.output()
-> output instrumentation
-> assistant aggregator
```

UltraVox path:

```text
transport.input()
-> instrumentation
-> UltraVox Realtime service
-> LLM/TTS instrumentation
-> transport.output()
-> output instrumentation
```

### Providers

Transports:

- Daily, kept for the original baseline.
- LiveKit, current main transport.

STT:

- Deepgram Nova-3, current baseline.
- Deepgram Flux, experimental.
- UltraVox native audio path, only in UltraVox mode.

LLM:

- Groq LLaMA 3.1 8B Instant, current cascade latency baseline.
- Gemini 2.5 Flash, diagnostic/quality comparison.
- OpenAI GPT-4o mini, integrated.
- Qwen, integrated but slow in observed test.
- xAI Grok 4.1 Fast non-reasoning, integrated but not yet winning.
- Mock immediate responder, for latency floor tests.
- UltraVox Realtime, audio-native path.

TTS:

- Cartesia Sonic-3, current cascade TTS.
- UltraVox native output in UltraVox mode.

### Instrumentation

Event and benchmark artifacts:

```text
data/verbatim/events.jsonl
data/verbatim/calls/{call_id}.json
data/verbatim/transcripts/{call_id}.jsonl
data/verbatim/slow_turns/{call_id}/{turn_id}.json
```

Each event includes:

```text
schema_version
session_id
call_id
turn_id
agent_id
client_id
event_name
timestamp_wall_iso
timestamp_monotonic_ms
provider
metadata
```

Important latency metrics:

```text
turn_detection_latency_ms
stt_final_latency_ms
transcript_ready_to_llm_enqueue_ms
llm_queue_latency_ms
llm_provider_ttfb_ms
llm_ttft_total_ms
first_token_to_3_words_ms
first_token_to_6_words_ms
first_token_to_speakable_phrase_ms
first_token_to_text_frame_ms
text_frame_to_tts_input_ms
tts_ttfb_ms
playback_latency_ms
perceived_response_latency_ms
transcript_ready_to_playback_ms
full_turn_duration_ms
```

Guard/quality counters:

```text
active_llm_cancelled_count
barge_in_before_audio_count
stale_llm_completed_count
phantom_turn_prevented_count
ultravox_playback_clear_buffer_count
echo_suppressed_count
```

Slow-turn classification buckets:

```text
turn_detection
stt_final
transcript_ready_to_llm_enqueue
llm_queue
llm_provider_ttft
llm_stream_gap
first_speakable_phrase
text_frame_to_tts_input
tts_ttfb
playback_delay
interruption_recovery
tool_call
unknown
```

## Current Telemetry Caveats

### Perceived Latency

For the cascade path, perceived latency is usually:

```text
assistant.playback_started_at - user.speech_stopped_at
```

For UltraVox, `user.speech_stopped_at` is often absent or not comparable. The dashboard now falls back to:

```text
assistant.playback_started_at - transcript.ready_at
```

The dashboard should label this as:

```text
perceived_latency_source=transcript_ready_to_playback
```

This prevents `n/a`, but it is not identical to human-perceived latency from the end of physical speech.

### P95

The percentile function uses nearest-rank percentile. With small sample sizes, p95 can look harsh or weird because one bad turn dominates. For example, with 5-10 turns, one spike can effectively become p95.

For serious decisions, compare:

```text
30+ turns per configuration
same transport
same STT
same LLM
same TTS
same prompt
same room/client conditions
```

### Historical Summary Files

Some existing `data/verbatim/calls/*.json` files were written before the latest analytics fallback/source changes. Current API recomputation from `events.jsonl` is more accurate for `perceived_latency_source`.

## Where Latency Is Lost Now

### Good Cascade Path

The good LiveKit + Nova-3 + Groq + Cartesia path usually looks like:

```text
Nova turn finalization: fast enough when endpointing works
Groq provider TTFT: often 90-180 ms
LLM queue: usually negligible
Cartesia first audio: usually 140-280 ms
Playback delay: usually small, but not always
```

That is how the system reaches the 400-700 ms felt band.

### Remaining Tail Sources

The bad 5 percent tends to come from:

1. STT/turn commit instability: long user sentences can still get split or committed too early.
2. TTS/output instability: some runs show voice cutouts or high TTS TTFB.
3. Interruption recovery: barge-ins and stale LLM/TTS work can distort both behavior and metrics.
4. LLM provider spikes: Groq average is strong, but p95 can still spike.
5. Conversation pattern failures: the model sometimes asks too many qualification questions, which creates longer speech and more chances for interruption.

## Conversation State

The current assistant character is Alicia:

```text
Role: warm female voice agent created by CRTG AI for CRTG Real Estate
Domain: Dubai real estate only
Style: relaxed concierge in her 20s
Behavior: conversational, not a form-filling script
Default response length: usually 4-10 words
Fallback close: follow up by WhatsApp
```

The system prompt now explicitly bans the most problematic patterns:

```text
"you're looking for"
"that's a great budget"
"sounds like"
"rent or purchase"
"what's your budget"
"which area"
"what property are we looking at"
```

The cascade path also has a response style guard that rewrites or drops common fast-model sales-bot recaps before they reach TTS.

Important limitation:

```text
The style guard can rewrite text LLM output before Cartesia speaks.
It cannot reliably rewrite UltraVox audio after UltraVox has already begun speaking.
```

So UltraVox conversation style depends much more heavily on prompt design and UltraVox-native controls.

## Known Open Problems

### 1. User Interruption Is Still Too Aggressive

The hard tradeoff:

```text
Short STT/turn timing -> low latency, but cuts off long user sentences.
Longer STT/turn timing -> fewer cutoffs, but latency moves back toward 800-1500+ ms.
```

Current cascade settings are aggressive:

```text
Deepgram endpointing: 100 ms
Deepgram utterance_end_ms: 1000 ms
final transcript fragment delay: 220 ms
final transcript eager commit: on
VAD-only user turn start: on
```

Next direction:

- Keep Nova-3 as baseline.
- Tune only one turn parameter at a time.
- Measure both latency and `user_utterance_split_count`.
- Keep `premature_assistant_start_count`, valid/false barge-ins, and suspected cutouts visible during tests.

### 2. Assistant Voice Cutouts

Observed symptom:

```text
The agent voice sometimes cuts out while speaking.
```

Possible sources:

- LiveKit output chunking/buffering.
- Browser audio constraints.
- VAD/barge-in falsely treating bot audio or user noise as interruption.
- UltraVox playback clear-buffer events.
- TTS streaming chunk boundaries.
- Network jitter.

Recent mitigation:

```text
VERBATIM_LIVEKIT_AUDIO_OUT_10MS_CHUNKS=4
VERBATIM_ULTRAVOX_MINIMUM_INTERRUPTION_DURATION_SECONDS=0.36
VERBATIM_ULTRAVOX_FRAME_ACTIVATION_THRESHOLD=0.2
VERBATIM_ULTRAVOX_CLIENT_BUFFER_SIZE_MS=80
```

Next direction:

- Add client-side audio received/playback metrics.
- Count playback clear-buffer events per turn.
- Compare bot audio cutouts with `ultravox.playback_clear_buffer`, `assistant.interrupted`, `turn.interrupted`, and LiveKit output events.
- Run a no-barge-in stability test with `VERBATIM_MUTE_USER_WHILE_BOT_SPEAKING=true` to isolate audio transport/TTS from interruption logic.

### 3. p95 Is Still Not Reliable Enough

Current target:

```text
Average: 500-700 ms
p95: under 1500 ms
```

Some runs now hit this. Others still spike over 2000 ms.

Next direction:

- Require 30-turn runs for claims.
- Split p95 by clean turns vs interrupted turns.
- Track first turn vs later turns.
- Track bottleneck class distribution at p95.
- Store full slow-turn JSON traces for every turn above p95.

### 4. LLM Style Still Needs Control

The fast Groq model has the right latency but can act "dumb" or repetitive:

- Repeats the user's context.
- Says obvious real-estate filler.
- Asks qualification questions too early.
- Ends up sounding like a form.
- Keeps the conversation moving when it should dwell casually.

Mitigations already in place:

- Short system prompt.
- Deterministic conversation-mode injection before each cascade LLM call.
- Hard bans on obvious patterns.
- Very short response cap.
- History limited to one message.
- Response style guard for cascade text output.

Current conversation modes:

```text
social
capability_explanation
appointment_booking
property_interest
human_handoff
repeat
stop_or_correction
goodbye
unknown
```

Next direction:

- Add transcript-based eval tests for each conversation mode.
- Extend the response guard if Groq finds a new form-question pattern.
- In social/check-in turns, continue banning property qualification entirely.
- In handoff/closing turns, prefer WhatsApp follow-up and stop asking.
- Add transcript-based eval tests for "does not ask a question after user says stop asking questions".

## What To Test Next

### Main Benchmark

Use:

```text
LiveKit + Nova-3 + Groq + Cartesia
```

Run:

```text
30 turns
same room setup
same browser/audio device
same prompt
no provider switching mid-run
```

Watch:

```text
avg_perceived_latency_ms
p95_perceived_latency_ms
perceived_latency_source
avg_transcript_ready_to_playback_ms
avg_llm_provider_ttfb_ms
avg_tts_ttfb_ms
active_llm_cancelled_count
stale_llm_completed_count
phantom_turn_prevented_count
bottleneck_counts
```

### Voice Cutout Isolation

Run one test with:

```text
VERBATIM_MUTE_USER_WHILE_BOT_SPEAKING=true
```

Expected interpretation:

- If cutouts disappear, interruption/barge-in policy is the likely issue.
- If cutouts remain, transport/TTS/browser audio is the likely issue.

### STT Sentence Completion Test

Use long, natural user sentences and count how often the agent starts replying before the thought is complete.

Example utterance:

```text
Hey, I saw a property on Bayut, but the price was not listed, and I wanted to know if you had anything similar but maybe not exactly in the same area.
```

Track:

```text
Was it split into multiple turns?
Did Alicia begin answering before the sentence ended?
Was perceived latency still under 700 ms?
```

### UltraVox Test

Use:

```text
LiveKit + UltraVox
```

Track separately:

```text
transcript_ready_to_playback
interruption count
playback clear-buffer count
voice cutout count
conversation style failures
```

UltraVox should only become the main path if it beats the cascade on both latency and interaction quality.

## Success Criteria For The Next Milestone

Verbatim should be considered "next-level stable" when the main stack can repeatedly produce:

```text
30-turn benchmark
avg perceived latency: 500-700 ms
p95 perceived latency: under 1500 ms
interruption mistakes: rare
assistant cutouts: rare or absent
conversation form-pattern failures: rare
no mixed metrics across calls/providers
```

The current state is close on latency, but not yet close enough on stability and conversational feel.

## Useful Files

Source:

```text
src/verbatim/config.py
src/verbatim/server.py
src/verbatim/pipeline/agent.py
src/verbatim/pipeline/pipecat_processors.py
src/verbatim/instrumentation/recorder.py
src/verbatim/analytics/latency.py
src/verbatim/livekit.py
src/verbatim/daily.py
static/index.html
static/app.js
static/styles.css
```

Docs and scripts:

```text
README.md
docs/latency_diagnostics.md
docs/manual_voice_test.md
scripts/summarize_latency.py
scripts/benchmark_direct_gemini_ttft.py
```

Data:

```text
data/verbatim/events.jsonl
data/verbatim/calls/
data/verbatim/transcripts/
data/verbatim/slow_turns/
```

## Current Bottom Line

The winning direction is:

```text
LiveKit + Nova-3 + Groq + Cartesia
```

It exists because LiveKit improved transport behavior, Nova-3 beat Flux in practical end-of-turn timing, Groq beat Gemini/OpenAI/Qwen/xAI on usable first-token latency, and Cartesia remains good enough that it is not the first thing to replace.

The main technical fight has shifted from "make it work" to:

```text
make p95 boring,
make interruptions polite,
make audio never cut out,
and make Alicia stop acting like a form.
```
