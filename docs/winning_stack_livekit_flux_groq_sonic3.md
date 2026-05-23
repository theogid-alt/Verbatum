# Verbatim Winning Stack: LiveKit + Flux + Groq + Sonic-3

Date recorded: 2026-05-19

## Current Winner

The current winning custom cascade is:

```text
LiveKit transport
-> Deepgram Flux STT
-> Groq LLaMA 3.1 8B Instant
-> Cartesia Sonic-3 TTS
```

This stack should be treated as the protected baseline. Do not change the bot pipeline, model choices, transport settings, prompt behavior, worker lifecycle, or TTS settings unless there is a specific benchmark reason and a rollback path.

## Exact UI Selection

Use the local console at `http://127.0.0.1:8000`.

Select:

```text
Transport: LiveKit
STT: Flux
LLM: Groq LLaMA 3.1 8B
TTS: Cartesia Sonic-3
```

The `.env` default may still show Nova-3 because the UI can override the STT choice per call. The winner is the LiveKit + Flux runtime selection.

## Required Environment Keys

Do not store secrets in docs. The winning stack requires these fields to be populated in `.env`:

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
DEEPGRAM_API_KEY
GROQ_API_KEY
CARTESIA_API_KEY
VERBATIM_CARTESIA_VOICE_ID
```

Useful non-secret model/config names:

```text
VERBATIM_GROQ_MODEL=llama-3.1-8b-instant
VERBATIM_CARTESIA_MODEL=sonic-3
```

Flux is selected through the UI as:

```text
stt_provider=deepgram_flux
deepgram_model=flux-general-en
```

## Why This Became The Winner

LiveKit became the best transport because it gave the cleanest low-latency WebRTC behavior once the Python worker isolation fix was added.

Deepgram Flux became the preferred STT for this stack because, in the latest run, it produced reliable turn handling and transcription in the LiveKit path.

Groq LLaMA 3.1 8B Instant became the best LLM baseline because it is fast enough for live voice and works well enough with a strict prompt.

Cartesia Sonic-3 remains the TTS baseline because it has consistently sounded good and avoided being the main latency bottleneck.

## Critical Fix That Made LiveKit Work

The important architecture fix was moving each Pipecat agent into a fresh worker process.

Before this, Daily and LiveKit could be loaded into the same long-running Python process. On macOS, the logs showed duplicate WebRTC Objective-C classes from both SDKs. That could create undefined behavior where LiveKit connected and subscribed to audio but no usable STT transcript appeared.

Now:

```text
FastAPI server
-> starts one agent worker process per call
-> worker runs Pipecat transport/STT/LLM/TTS
-> stopping or starting a new call kills the previous worker
```

Relevant files:

```text
src/verbatim/server.py
src/verbatim/agent_worker.py
src/verbatim/pipelines/pipecat.py
```

The server passes the chosen provider settings into the worker:

```text
transport_provider
room_url
room_token
room_name
call_id
session_id
stt_provider
deepgram_model
llm_provider
llm_model
```

The worker applies those overrides and runs `run_voice_agent(...)`.

## Current Pipeline Shape

The cascade pipeline is:

```text
transport.input()
-> input probe
-> STT
-> STT probe
-> user context aggregator
-> pre-LLM probe
-> LLM
-> LLM probe
-> identity bleed guard
-> TTS
-> TTS probe
-> transport.output()
-> output probe
-> assistant context aggregator
```

Pipecat metrics are enabled:

```text
enable_metrics=True
enable_usage_metrics=True
report_only_initial_ttfb=False
```

Audio settings in the cascade task:

```text
audio_in_sample_rate=16000
audio_out_sample_rate=24000
```

LiveKit transport settings:

```text
audio_in_enabled=True
audio_out_enabled=True
video_in_enabled=False
video_out_enabled=False
```

Flux STT settings are loaded from env/config:

```text
deepgram_flux_eager_eot_threshold
deepgram_flux_eot_threshold
deepgram_flux_eot_timeout_ms
deepgram_flux_min_confidence
```

## Current Prompt Direction

The current Groq cascade prompt is intentionally short and strict:

```text
Answer the caller's actual question first.
Do not block simple questions behind qualification questions.
If they ask for price, answer or say you can send it by SMS.
After discussing a specific property, gently offer to book a property viewing.
After a viewing is booked, offer to send an SMS confirmation.
Ask at most one useful follow-up question.
Do not repeat or rephrase what the caller said.
Avoid form-like questions unless the caller asks for recommendations.
Keep replies very short.
Do not claim a company, city, or name unless provided.
```

This prompt is part of the winning behavior. Do not expand it into a long sales script without benchmarking, because longer prompts previously made the agent more rigid and slower-feeling.

## What Not To Touch

Do not change these while preserving the winning baseline:

```text
Transport: LiveKit
STT selection: Flux
LLM provider/model: Groq / llama-3.1-8b-instant
TTS provider/model: Cartesia / sonic-3
Per-call worker process isolation
Short Groq prompt
Cartesia sentence aggregation unless benchmarking says otherwise
One active agent at a time
```

Daily and Hume remain useful comparison paths, but they are not the current winner.

## Dashboard Metrics

Dashboard metrics were reconnected on 2026-05-19.

Recent dashboard additions:

```text
Pre-call KB input.
Generated brief call summary.
Tool terminal status lines for started / succeeded / needs confirmation / failed.
```

Current safe business tools:

```text
Nango-backed Google Calendar property viewing availability and booking.
Twilio SMS viewing confirmation.
```

The expected event/log path is:

```text
data/verbatim/events_v2_clean.jsonl
data/verbatim/transcripts_v2_clean/
data/verbatim/calls_v2_clean/
```

The summarizer now supports the normalized v2 dotted event names emitted by the worker:

```text
transcript.user
llm.request.started
llm.first.token
tts.request.started
tts.first.audio
assistant.playback.started
assistant.completed
livekit.client.stats
```

The dashboard should show the active call's perceived latency, p95, provider TTFT, TTS first audio, playback delay, error count, config line, transcript, and LiveKit browser network stats.

STT processing is tracked as:

```text
user.speech.stopped -> transcript.user
```

This measures the time from detected end-of-user-speech to final transcript availability.

Metrics must stay scoped to the selected `call_id`; do not aggregate Hume, Daily, or stale LiveKit calls into the active run.

Useful diagnostic events already added:

```text
livekit.client.microphone_enabled
audio.input_first_frame
transport.audio_subscribed
transcript.user
```

If LiveKit ever stops transcribing again, check the events in this order:

```text
livekit.client.microphone_enabled
transport.audio_subscribed
audio.input_first_frame
transcript.user
```

That sequence tells us whether the failure is browser mic publishing, LiveKit transport subscription, Pipecat input frames, or STT transcription.

## Baseline Preservation Rule

Any future experiment should be run against a copy or with an explicit rollback note. The current winner should stay reproducible from this document.
