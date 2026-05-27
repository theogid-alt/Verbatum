# Verbatim v02.3 Repeated Issue Summary

## Source

Latest reviewed folder:

```text
data/verbatim/evaluations/v02.3/
```

Saved evaluations reviewed: 11.

Average scores:

| Area | Average |
| --- | ---: |
| Overall | 3.47 |
| Realism | 3.91 |
| Tool calling | 3.45 |
| Latency | 3.80 |
| STT | 3.73 |
| Intelligence | 3.36 |
| Task success | 2.91 |
| Conversation flow | 4.00 |
| Faithfulness / safety | 2.64 |

## Repeated Issues

### 1. Property-Detail SMS Claims

Several notes said the agent claimed it could send property details, links, or information by SMS, but the system only had a viewing-confirmation SMS path. v0.3 adds a property-detail SMS path through the same safe Twilio tool.

### 2. Mid-Sentence Guard Fallback

The phrase `I can help with that` appeared inside otherwise normal sentences. This came from the identity-bleed guard replacing one streamed LLM chunk mid-response. v0.3 now suppresses that blocked chunk instead of injecting a spoken fallback phrase.

### 3. Booking Slot Guidance

The agent sometimes waited for the caller to propose a time, even though callers do not know calendar availability. v0.3 allows the direct calendar layer to suggest available viewing slots when the caller asks to visit/book without a full day/time.

### 4. Booking SMS Missing Address Context

Booking confirmations said the viewing was booked but did not tell the caller where to meet. v0.3 adds an address to the SMS when the KB contains an `Address:` or `Location:` line. If no address is present, the SMS says an agent will send the address before the viewing.

### 5. Date Parsing / Wrong Year

One serious repeated-style risk appeared in v02.3: month/day corrections like `May 27` could be misread through weekday fallback and lead to the wrong week or year. v0.3 parses explicit month-day phrases before weekday fallback and rejects `never mind` / correction turns as booking confirmations.

## Not Fixed In v0.3

- Generic property hallucination is mostly expected to be solved by stronger KB content.
- Minor STT mumbles and first-word cutoff were isolated and not worth changing the winning STT setup.
- Occasional latency spikes remain tracked through p95 and peak counts, but v0.3 does not change the core voice stack.

## v0.3 Fix Scope

v0.3 keeps the winning stack unchanged:

```text
LiveKit -> Deepgram -> Groq -> Cartesia
```

Only prompt/tool guardrails, property SMS handling, booking-slot suggestions, booking SMS text, date parsing, and version labels changed.

