# Verbatim V2 Baseline

Verbatim v2 is a reset of the local demo app. The old implementation is archived in:

```text
archive/legacy_2026-05-18/
```

The new app keeps the same `.env` keys but reduces the runtime to three clear modes:

```text
LiveKit + Pipecat cascade
Daily + Pipecat cascade
Hume EVI direct comparison
```

The original v2 custom cascade was:

```text
LiveKit -> Deepgram Nova-3 -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

The current winning benchmark stack is now recorded separately:

```text
LiveKit -> Deepgram Flux -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

See:

```text
docs/winning_stack_livekit_flux_groq_sonic3.md
```

## Current Situation Snapshot

Updated: 2026-05-23

The protected benchmark winner remains:

```text
LiveKit -> Deepgram Flux -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

The active `.env` default currently starts from:

```text
LiveKit -> Deepgram Nova-3 -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

Flux can still be selected in the dashboard and should be treated as the current winning-stack selection when benchmarking. Keep this distinction clear: `.env` defaults are boot convenience, while the protected winner is the benchmarked UI selection.

Current product capabilities:

```text
Pre-call KB pasted directly into the dashboard.
Generated post-call summary in the call notes panel.
Terminal tool-status lines for tool started / succeeded / needs confirmation / failed.
Nango-backed Google Calendar viewing tools.
Twilio SMS viewing confirmation.
Calendar bookings framed as property viewings.
SMS follow-up framed as viewing confirmation.
```

Detailed roadmap comparison and next-step planning live in:

```text
docs/current_state_against_roadmap_may_september.md
```

Telemetry is intentionally small. New v2 events use `schema_version=verbatim.v2` and should be written to:

```text
./data/verbatim/events_v2_clean.jsonl
./data/verbatim/transcripts_v2_clean/
./data/verbatim/calls_v2_clean/
```

Do not port old speculative EOT logic, style rewrites, or p95 heuristics into v2 until the baseline is stable.
