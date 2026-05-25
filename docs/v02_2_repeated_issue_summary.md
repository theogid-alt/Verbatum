# Verbatim v02.2 Repeated Issue Summary

## Source

Latest reviewed folder:

```text
data/verbatim/evaluations/v02.2/
```

Saved evaluations reviewed: 5.

Average scores:

| Area | Average |
| --- | ---: |
| Overall | 3.19 |
| Realism | 3.80 |
| Tool calling | 1.75 |
| Latency | 3.60 |
| STT | 3.80 |
| Intelligence | 3.20 |
| Task success | 1.75 |
| Conversation flow | 3.80 |
| Faithfulness / safety | 3.00 |

Average telemetry from the saved reports:

| Metric | Average |
| --- | ---: |
| Perceived latency | 1249 ms |
| Perceived p95 | 3526 ms |
| Normal-turn p95 | 3526 ms |
| Tool-turn p95 | 1196 ms |
| Tool calls | 1.6 / call |
| Tool failures | 0.2 / call |

## Repeated Issues

### 1. Tool Truth Is Still The Main Problem

Multiple notes mention fake or impossible booking/SMS behavior:

- The agent said it would book after the call.
- The agent said the caller could hang up while booking/SMS work happened later.
- The agent implied SMS or booking follow-up even when no booking had happened.
- The agent sometimes failed to close the booking flow cleanly.

This is the only repeated issue severe enough to justify code changes in v02.3.

### 2. Split Booking Details Need Better Recovery

The caller often gives booking details across several short STT turns, for example:

```text
Monday works.
Morning maybe 6:30 AM.
Can you book it?
```

The agent sometimes asked for the day or time again instead of preserving those fragments.

### 3. Identity Fallback Sounds Robotic

One note mentions the agent randomly saying a variant of:

```text
I help with real estate questions.
```

That phrase comes from the identity-bleed fallback guard. It is useful as a safety guard, but the wording is too noticeable.

## Ignored One-Offs

These were not fixed because they appeared as isolated outliers or are safer to observe for another batch:

- One Bayut transcription issue.
- One assumed-property issue.
- One generic high-latency note.
- Single-call conversational awkwardness not repeated across the batch.

## v02.3 Fix Scope

v02.3 intentionally does not change the winning voice stack:

```text
LiveKit -> Deepgram -> Groq -> Cartesia
```

The patch only changes:

- Tool-truth prompt guidance.
- LLM output guard for post-call booking/SMS promises.
- Booking-detail fragment memory across short STT turns.
- Identity fallback wording.
- Default evaluation version label.

