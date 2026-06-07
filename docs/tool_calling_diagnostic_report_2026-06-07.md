# Verbatum Tool-Calling Diagnostic Report

Date: 2026-06-07

## Scope

This diagnostic pass does not change the tool-calling architecture.

The current architecture remains:

```text
LiveKit
-> Deepgram
-> direct calendar/SMS intent processor
-> SchedulingService gates
-> Groq LLaMA 3.1 8B
-> LLM truth guard
-> Cartesia
```

Groq native tool schemas remain disabled. The direct processor remains active.

## What Was Added

Tool interactions are now traced end to end through JSONL events:

```text
tool.intent.parsed
tool.intent.unresolved
tool.direct.activated
tool.direct.skipped
tool.execution.result
tool.assistant.response
tool.call.started
tool.call.completed
tool.call.failed
```

Each traced interaction can now show:

```text
user_request
parsed_intent
tool_selected
tool_arguments
tool_execution_result
tool_execution_succeeded
assistant_response
assistant_response_matched_reality
```

A new dashboard section, **Tool Diagnostics**, shows:

```text
tool selection accuracy
parameter accuracy
hallucinated success rate
tool execution failure rate
booking success rate
SMS success rate
50-scenario pass rate
failure-source ranking
recent tool interactions
```

## Automated Scenario Harness

The offline harness contains 50 scenarios across:

```text
booking
rescheduling
cancellation
availability lookup
ambiguous dates
missing information
invalid requests
double bookings
SMS follow-up
user correction
```

The harness classifies failures into:

```text
A. Intent detection
B. Parameter extraction
C. Tool execution
D. Tool result handling
E. Assistant response generation
```

## Current 50-Scenario Result

```text
Total scenarios: 50
Passed: 40
Failed: 10
Pass rate: 80.0%
```

Failure-source ranking:

| Rank | Source | Count | Meaning |
|---:|---|---:|---|
| 1 | A. Intent detection | 8 | The system picked the wrong tool, wrong intent, or no tool. |
| 2 | B. Parameter extraction | 2 | The system picked the right rough tool but extracted the wrong/missing parameters. |
| 3 | C. Tool execution | 0 | No simulated failures originated from Nango/Twilio/service execution. |
| 4 | D. Tool result handling | 0 | Current canned result responses matched simulated results. |
| 5 | E. Assistant response generation | 0 | No hallucinated success in the offline direct-tool scenario harness. |

## Failed Scenarios

```text
reschedule_02: A - "Move my appointment to tomorrow at noon."
availability_02: A - "Can I come by tomorrow at 11 AM?"
availability_03: A - "Do you have any slots next week?"
availability_04: B - "What availability do you have on June 25th?"
availability_06: A - "Can we do that time?"
ambiguous_01: A - "Can we do next week?"
invalid_04: A - "Read me everything on your calendar."
invalid_05: A - "Book a viewing before I know the price."
double_04: A - "Are you already busy Friday at 2 PM?"
correction_02: B - "Wait, make it Saturday at 1 PM."
```

## Main Finding

The biggest current source of tool failure is **not tool execution** and not native provider latency.

The biggest current source is:

```text
Intent detection
```

The direct processor is still brittle around:

```text
rescheduling language
availability phrasing
relative slots such as "that time"
unsupported calendar-read requests
negative intent such as "before I know the price"
mid-conversation corrections
```

The second source is:

```text
Parameter extraction
```

Especially when the user corrects a prior slot or gives a date phrase that the parser partially recognizes but does not attach correctly.

## Interpretation

This supports the current decision not to replace the architecture yet.

The tool services already have useful lower-level gates:

```text
pending booking required
explicit confirmation required
conflict check before calendar write
idempotent repeated confirmation
safe missing-connection failure
safe timeout failure
SMS destination constrained to caller phone
```

The problem is earlier in the pipeline:

```text
spoken user request -> direct intent/action object
```

Before considering native Groq tool calling, the next engineering focus should be measuring and improving direct intent routing and parameter extraction.

## Next Recommended Fix Area

Do not change the architecture globally.

The next targeted fix should be:

```text
Build a clearer deterministic tool-intent state machine around booking, availability, rescheduling, cancellation, and SMS.
```

Specifically:

```text
1. Separate "availability check" from "booking request" more strictly.
2. Add explicit reschedule intent as its own first-class path.
3. Track last proposed/confirmed slot and use it for "that time" only when fresh.
4. Reject or defer unsafe requests like "book before I know the price."
5. Improve correction handling so "wait, make it Saturday" replaces the prior slot instead of reusing it.
```

The new instrumentation should make each future failure obvious:

```text
Did the parser miss the intent?
Did it extract the wrong date/time?
Did the tool fail?
Did the response misstate the tool result?
```

That is the diagnostic foundation needed before changing the architecture or trying native Groq tools.
