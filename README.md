# Verbatim V2 Voice-Agent Baseline

Verbatim v2 is a clean reset of the local WebRTC voice-agent demo. The old implementation is archived at:

```text
archive/legacy_2026-05-18/
```

The current app keeps your existing `.env` keys and supports three first-class modes:

```text
LiveKit + Pipecat cascade
Daily + Pipecat cascade
Hume EVI direct comparison
```

The original v2 custom baseline is:

```text
LiveKit -> Deepgram Nova-3 -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

The current winning benchmark stack is:

```text
LiveKit -> Deepgram Flux -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

Preservation notes are in:

```text
docs/winning_stack_livekit_flux_groq_sonic3.md
```

Hume remains available in the UI for comparison.

## Tool Calling

Tool calling runs by default on compatible Pipecat cascade calls when at least one safe tool backend is ready. Benchmark-only calls can still disable it with `VERBATIM_TOOLS_ENABLED=false`.

## Concurrent Calls

The local dashboard used to enforce one active bot globally to prevent orphan test agents. The server now allows one isolated worker per `call_id`, capped by:

```bash
VERBATIM_MAX_ACTIVE_AGENTS=8
```

Starting the same `call_id` twice returns `already_running` instead of creating a duplicate bot. The dashboard stop button stops the current call only; `POST /api/agent/stop` can still stop all workers with `{"stop_all": true}` for cleanup.

The dashboard terminal shows safe tool facts while a call is running, including `calendar_checked`, `calendar_has_conflict`, `booking_booked`, `sms_sent`, `to_phone`, and duration. Calendar writes still require a confirmed booking path; SMS confirmation is sent only after a real booking exists.

## Local Client Kit

Verbatim now works as a cloneable local operator kit. Each cloned folder creates local client files on first dashboard load:

```text
client/profile.json
client/prompt.md
client/kb.md
client/integrations.json
```

These files are ignored by git so client-specific prompts, KB, and enabled integrations stay local to that cloned agent folder. The dashboard edits them with explicit Save buttons, then uses the saved prompt and persistent KB automatically on calls. Integration cards show what is configured, missing from `.env`, connected, disabled, or coming soon. Secrets still live only in `.env`.

The first client-owned integration path is Nango-backed Google Calendar:

```bash
NANGO_SECRET_KEY=
NANGO_API_BASE_URL=https://api.nango.dev
NANGO_GOOGLE_CALENDAR_INTEGRATION_ID=google-calendar
VERBATIM_DEFAULT_CLIENT_ID=demo
VERBATIM_TOOLS_ENABLED=true
VERBATIM_TOOL_TIMEOUT_MS=2500
```

The UI can create a Nango Connect link for a `client_id` and check connection status. Alicia only sees Verbatim-owned scheduling tools: exact availability/conflict checks, booking proposal/confirmation, and removal of Verbatim-created bookings. Calendar writes require explicit user confirmation, and busy slots are checked before writing.

Direct SMS follow-up is available through Twilio:

```bash
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_MESSAGING_SERVICE_SID=
```

Alicia asks the caller for their phone number, repeats it back for confirmation, and then sends a short SMS confirmation after a clear yes. The caller's number is held in call memory, not hard-coded in `.env`. Provider keys stay server-side, and tool events log only safe metadata.

## Setup

Install dependencies:

```bash
uv sync --extra dev
```

Fill in `.env` using the existing fields. The important keys for the default cascade are:

```bash
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
GROQ_API_KEY=
CARTESIA_API_KEY=
VERBATIM_CARTESIA_VOICE_ID=
```

For Daily comparison, also set:

```bash
DAILY_API_KEY=
```

For Hume comparison, also set:

```bash
HUME_API_KEY=
HUME_SECRET_KEY=
HUME_EVI_CONFIG_ID=
HUME_EVI_CONFIG_VERSION=
HUME_EVI_USE_CONFIG=false
HUME_EVI_VOICE_ID=
```

## Run

Detached server:

```bash
scripts/start_detached_server.sh
```

Stop it:

```bash
scripts/stop_detached_server.sh
```

Development server:

```bash
uv run uvicorn verbatim.server:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Test Flow

1. Select `LiveKit`, `Nova-3`, and `Groq`.
2. Click `Create Room`.
3. Click `Start Agent`.
4. Click `Join`.
5. Allow microphone access.
6. Watch the terminal, transcript, and latency panel.

For Hume, select `Hume EVI`, click `Create Hume Session`, then `Join`.

## V2 Telemetry

V2 writes a smaller event stream:

```text
./data/verbatim/events_v2_clean.jsonl
./data/verbatim/transcripts_v2_clean/{call_id}.jsonl
./data/verbatim/calls_v2_clean/{call_id}.json
```

Summarize latency:

```bash
uv run verbatim-latency --call-id call_xxx
```

The v2 dashboard intentionally tracks only the stable core metrics: perceived latency, provider TTFT, TTS first audio, playback delay, errors, transcript, and browser connection stats.

## Offline Evaluation

The evaluation layer is manual and post-call only. It reads existing v2 events, transcript logs, and call notes, then saves reviewer scorecards without touching the live agent worker.

```text
./client/evaluation_rubric.json
./data/verbatim/evaluations/{bot_version}/{call_id}.json
./data/verbatim/evaluation_runs/{run_id}.json
```

Open the dashboard and click `Evaluate Current Call` after a test call. Set the bot version, for example `v01` or `v02`, score each field from 1-5, add optional notes, then click `Save Evaluation`. The summary endpoint groups reports by version so 100-call batches can be averaged cleanly. The v2 rubric is benchmark-inspired, with fields for realism, tool calling, latency, STT, intelligence, task success, conversation flow, and faithfulness/safety. No LLM judge, audio recording, or automatic pass/fail is enabled in v1.

Current evaluation practice is iterative: fix obvious repeated issues as they appear, then move toward a stable release candidate. The near-term selling gate is 30 stable calls averaging above 4.0, with no repeated false tool claims, before heavier advertising.
