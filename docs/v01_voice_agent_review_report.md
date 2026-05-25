# Verbatim v0.1 Voice Agent Review Report

Generated: 2026-05-25

## Executive Summary

Verbatim v0.1 is now a real working voice-agent prototype, not just a pipeline experiment. The current system can run low-latency WebRTC calls, speak through Cartesia, transcribe through Deepgram, respond through Groq, use a local KB, create call summaries, and expose Google Calendar / Twilio SMS tools through the dashboard.

The strongest result from the v0.1 review cycle is that the core cascade is viable:

```text
LiveKit -> Deepgram -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

The weaker result is that the product is not ready to advertise yet. The voice layer is promising, but the system is still too hit-or-miss around tool truthfulness, p95 latency, prompt consistency, and telephony deployment. In several reviewed calls, the agent claimed that a booking or SMS happened when the external tool did not actually complete. That is the main trust blocker.

## Review Dataset

This report uses the saved local v0.1 evaluation reports:

```text
data/verbatim/evaluations/v01/
```

Current saved v0.1 evaluations:

```text
10 calls
```

This is useful directional feedback, but not enough for launch-level confidence. A stronger release gate should use at least:

```text
100 calls per bot version
30+ tool-heavy calls
30+ long natural utterance calls
20+ interruption / recovery calls
20+ telephony or SIP calls once SIP exists
```

## Current Stack

### Current Custom Cascade

The protected custom stack remains:

```text
LiveKit transport
Deepgram STT, currently Nova-3 and Flux selectable
Groq LLaMA 3.1 8B Instant
Cartesia Sonic-3 TTS
```

The documented winning benchmark stack is:

```text
LiveKit -> Deepgram Flux -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

The v0.1 saved evaluations currently include calls using:

```text
LiveKit
Deepgram Nova-3
Groq LLaMA 3.1 8B Instant
Cartesia Sonic-3
```

This means future evaluations must be stricter about version labels. A report should never compare `v01` without knowing whether that means Nova or Flux, which prompt was active, which KB was loaded, and whether tools were enabled.

### Current Product Capabilities

Working or partially working today:

```text
WebRTC test dashboard
LiveKit transport
Daily comparison path
Hume comparison path
Provider selectors
Persistent local client profile
Editable local prompt
Persistent local KB
Generated post-call summary
Manual post-call evaluation scorecard
Versioned evaluation storage
Google Calendar integration through Nango
Twilio SMS follow-up
Tool status terminal lines
Latency metrics panel
Browser network stats for LiveKit
```

Still not production-ready:

```text
SIP trunking / real phone-number routing
Reliable booking/SMS truth enforcement
Launch-grade p95 latency
Prompt/persona consistency under longer calls
Professional benchmark harness
Integration onboarding flow
Deployment packaging per client
Monitoring/alerts
Human handoff
Call recording / transcript storage policy
```

## v0.1 Evaluation Score Summary

Average human-review scores across the 10 saved v0.1 evaluations:

| Domain | Average | Interpretation |
|---|---:|---|
| Task success | 4.2 / 5 | The agent often moves the call forward. |
| Intelligence | 3.7 / 5 | Good enough for simple real-estate demos, but still brittle. |
| Realism | 3.3 / 5 | Promising, but not consistently human-feeling. |
| STT | 3.33 / 5 | Generally usable, with occasional outcome-changing misses. |
| Conversation flow | 3.3 / 5 | Still has form-like or premature assumptions. |
| Latency | 3.0 / 5 | Average can be acceptable, but p95 is not. |
| Tool calling | 2.7 / 5 | Main operational weakness. |
| Faithfulness / safety | 2.1 / 5 | Main trust weakness. |

The review scores say something very clear:

```text
The agent can have a useful conversation, but cannot yet be trusted to always tell the truth about external actions.
```

## v0.1 Latency Summary

Average metrics across the 10 saved v0.1 evaluations:

| Metric | Average |
|---|---:|
| Average perceived latency | 1354 ms |
| p95 perceived latency | 3749 ms |
| Average provider TTFT | 230 ms |
| p95 provider TTFT | 758 ms |
| Average STT processing | 211 ms |
| p95 STT processing | 572 ms |
| Average TTS first audio | 164 ms |
| p95 TTS first audio | 191 ms |
| Average tool calls per reviewed call | 6.4 |
| Average tool failures per reviewed call | 0.9 |
| Logged system errors | 0 |

The good news:

```text
Groq TTFT is fast.
Cartesia first audio is fast.
Deepgram STT processing is often fast enough.
The stack does not appear to be crashing.
```

The bad news:

```text
p95 perceived latency is still far too high.
Some perceived latency spikes are not caused by provider TTFT or TTS.
Tool turns and stalled orchestration can create long waits.
The dashboard needs to split normal turns from tool turns more aggressively.
```

For a sales demo, the goal should be:

```text
Clean p95 perceived latency: <900 ms
Real p95 perceived latency: <1500 ms
Tool-turn p95: measured separately
False booking/SMS claims: 0
```

## What Users Liked

### 1. The voice stack can feel fast

The best runs feel close to real-time. The system has reached call moments around the 400-700 ms perceived range, which is the right emotional zone for a voice demo.

### 2. The cascade is flexible

The current architecture allows provider comparison without rewriting the whole app:

```text
LiveKit / Daily / Hume
Nova-3 / Flux
Groq / Gemini / OpenAI / xAI / Qwen / Mock
Cartesia
```

This flexibility matters because the “best” provider may change.

### 3. The local client kit direction is right

The dashboard can now operate like a cloneable local operator kit:

```text
edit prompt
edit KB
toggle integrations
test calls
evaluate calls
repeat for another client folder
```

That matches the current MVP business model better than a SaaS onboarding system.

### 4. KB and brief call summaries are useful

The KB gives the agent local business context without adding a complex hosted backend. The post-call summary is the right shape: short, operational, and useful after a test call.

## Main Problems From v0.1 Reviews

### Problem 1: Tool Truthfulness

This is the biggest product blocker.

Observed failures:

```text
Agent says a viewing was booked when Google Calendar was not updated.
Agent says an SMS was sent when Twilio did not send anything.
Agent claims availability before checking the calendar.
Agent books or suggests the wrong date/time.
Agent asks for confirmation again after booking.
Agent treats failed tool state as if it succeeded.
```

Representative review notes:

```text
fake sms, fake booking
no kb, no sms, no booking, but lied
booked wrong day, no sms
did not use the tools and lied, google calendar not updated and sms not sent
```

Root cause:

```text
The LLM is sometimes allowed to answer tool-sensitive turns directly.
```

Correct policy:

```text
For booking/SMS/calendar turns, the LLM should not be the source of truth.
Only tool results should decide whether Alicia says booked, sent, available, busy, failed, or not connected.
```

Required fixes:

```text
1. Route all calendar/SMS intent through deterministic handlers before the LLM.
2. Add hard forbidden phrases for the LLM when no successful tool result exists:
   - "I booked"
   - "it is booked"
   - "I sent"
   - "you will receive"
   - "confirmation sent"
3. Only generate booking/SMS success language from confirmed tool results.
4. Store a per-call tool state machine:
   - no_booking
   - availability_checked
   - slot_offered
   - booking_pending_confirmation
   - booking_confirmed
   - sms_offered
   - sms_sent
   - sms_failed
5. Add evaluation flags for:
   - fake_booking_claim
   - fake_sms_claim
   - wrong_slot_booked
   - duplicate_booking_attempt
```

### Problem 2: p95 Latency Is Too High

Average latency is sometimes acceptable, but p95 is not.

Current v0.1 aggregate:

```text
avg perceived: 1354 ms
p95 perceived: 3749 ms
```

The p95 means a small number of turns feel very slow. That matters more than the average because a voice agent is judged by awkward silences.

What seems strong:

```text
Groq provider TTFT average around 230 ms
Cartesia first audio average around 164 ms
STT processing average around 211 ms
```

What still needs investigation:

```text
transcript-to-LLM delay
tool-turn orchestration delay
long-utterance split behavior
network jitter / packet loss
turns where assistant waits even though transcript is ready
```

Required fixes:

```text
1. Split p95 by normal turns vs tool turns.
2. Track transcript_ready -> tool_started -> tool_done -> assistant_playback.
3. Track transcript_ready -> llm_request_started for every turn.
4. Add a slow-turn report automatically for every turn over 1500 ms.
5. Keep the core voice path stable; do not keep changing STT/LLM/TTS while debugging tools.
```

### Problem 3: Prompt / Persona Consistency

The agent has improved, but reviews still show persona issues:

```text
doesn't know her own name
does not know its own name or business
acts like it knows my request before I have said anything
pretended it knew my request before I even asked
```

This is not just copywriting. It affects trust. A caller will forgive a slightly short answer; they will not forgive a confident wrong premise.

Required fixes:

```text
1. Keep a short identity block in the prompt.
2. Never let the prompt claim a city/company unless it is in the local client profile.
3. Add explicit rule: do not assume the caller's request before they state it.
4. Add a "do not pre-answer" style check in evaluation.
5. Store the active prompt snapshot with every call/evaluation.
```

### Problem 4: STT Is Usable But Still Impacts Outcomes

STT average scores are acceptable, but the reviews show that mis-heard dates, phone numbers, and split utterances can cause tool failures.

The biggest STT-sensitive fields are:

```text
date
time
phone number
property type
area
buy vs rent
```

Required fixes:

```text
1. Treat date/time as structured slots, not casual text.
2. Repeat only critical structured values before writes:
   - "I have tomorrow at 7:30 PM. Should I book that?"
3. Avoid user-spoken phone numbers for now.
4. Prefer caller phone from telephony metadata once SIP exists.
5. Add a date/time parser test set from actual transcripts.
```

### Problem 5: Integration Surface Is Promising But Still Early

The dashboard card system is the right MVP direction. It lets the operator connect/disconnect integrations without recoding every client.

But the integration layer is not launch-grade yet.

Current reality:

```text
Google Calendar and Twilio are the only meaningful live external tools.
Other cards are integration placeholders or connection/status scaffolding.
Nango connection state can be confusing.
Tool success/failure needs to be visible in plain language.
```

Required fixes:

```text
1. Add a "Tool Health" panel:
   - Calendar connected
   - Calendar read test passed
   - Calendar write test passed
   - Twilio configured
   - Twilio test SMS sent
2. Add a pre-call tool readiness checklist.
3. Block tool-enabled calls when a required tool is unhealthy, unless the operator intentionally allows fallback mode.
4. Add "test booking in sandbox calendar" before real calls.
5. Add clear local integration state reset.
```

## Current Strengths

Verbatim v0.1 is strongest in these areas:

```text
Fast WebRTC custom cascade
Good TTS quality
Good LLM TTFT with Groq
Functional local dashboard
Editable prompt and KB
Versioned evaluation system
Early integration cards
Manual review workflow
Cloneable client-folder direction
```

These are real assets. The system is no longer an abstract research prototype.

## Current Weaknesses

Verbatim v0.1 is weakest in these areas:

```text
Tool-call truth enforcement
External action reliability
p95 latency stability
Prompt/persona consistency
SIP/telephony absence
Integration health visibility
Benchmark discipline
Production deployment shape
```

The core voice stack feels like it can become a product. The surrounding reliability layer is not there yet.

## Recommended v0.2 Direction

### v0.2 Goal

The next version should not chase more providers. It should make the current stack trustworthy.

Target:

```text
LiveKit WebRTC demo remains the test surface.
Booking/SMS tool truthfulness becomes strict.
p95 latency becomes explainable.
Each call can be evaluated under a version label.
The same client kit can be cloned and edited repeatedly.
```

### v0.2 Release Criteria

Before calling v0.2 successful:

```text
30 reviewed real-estate calls
0 fake booking claims
0 fake SMS claims
0 wrong-date/wrong-time bookings
Calendar booking success rate >90% on valid requests
SMS confirmation success rate >90% when Twilio is configured
Clean-turn p95 <1200 ms
Real-turn p95 <2000 ms
Tool-turn p95 reported separately
Prompt identity failure <=1 per 30 calls
```

### Priority 1: Tool-State Machine

Implement a strict call-local state machine:

```text
property_discussed
viewing_offered
slot_requested
availability_checked
slot_available
slot_unavailable
booking_confirmation_requested
booking_confirmed
booking_failed
sms_confirmation_offered
sms_sent
sms_failed
```

Then force responses from state:

```text
If booking_confirmed is false:
  Alicia cannot say "booked."

If sms_sent is false:
  Alicia cannot say "sent."

If availability_checked is false:
  Alicia cannot say "we're free."
```

### Priority 2: Tool-First Routing

Calendar/SMS intent should bypass the LLM unless the deterministic layer returns "not a tool turn."

Tool-first phrases:

```text
book a viewing
can we do tomorrow
are you free
is that available
did you book it
is it on the calendar
send confirmation
did you send it
I have not received it
```

The LLM can still choose wording after the tool result, but it cannot invent the result.

### Priority 3: Evaluation Version Discipline

Each test call must save:

```text
bot_version
transport
STT provider/model
LLM provider/model
TTS provider/model
prompt snapshot
KB snapshot hash
enabled integrations
tool health snapshot
network snapshot
```

This prevents `v01` from becoming a blurry label that mixes different stacks.

### Priority 4: Latency Debugging By Category

Add separate views:

```text
Normal turns
Tool turns
Interrupted turns
Long user utterance turns
First turn
Bad network turns
```

For each category:

```text
avg perceived
p95 perceived
STT processing
transcript-to-LLM
provider TTFT
TTS first audio
playback delay
tool duration
```

### Priority 5: SIP / Telephony Planning

Do not advertise before SIP exists, but start designing around it now.

Needed telephony pieces:

```text
SIP trunk / phone number provider
inbound call routing to LiveKit or equivalent
caller phone metadata
DTMF / human transfer path
call recording policy
business-hours routing
fallback when agent fails
hangup detection
post-call transcript and summary storage
production monitoring
```

Caller phone metadata matters because it solves the phone-number transcription problem. The agent should not ask callers to spell a phone number if the call already provides ANI/caller ID.

## Suggested v0.2 Work Plan

### Week 1: Tool Reliability

```text
Add strict tool-state machine.
Block LLM booking/SMS claims without tool success.
Add Calendar/Twilio health checks.
Add tool-turn evaluation flags.
Run 30 tool-heavy calls.
```

### Week 2: Latency Visibility

```text
Separate normal/tool/interrupted latency.
Add slow-turn reports.
Add p95 contributor table.
Fix transcript-to-LLM stalls.
Run 50 mixed calls.
```

### Week 3: Client Kit Hardening

```text
Save prompt snapshot per call.
Save KB snapshot hash per call.
Add integration readiness checklist.
Add one-click reset for local tool state.
Document clone-and-configure workflow.
```

### Week 4: SIP Feasibility Spike

```text
Pick SIP path.
Prototype inbound call to the same agent stack.
Pass caller number into session.caller_phone.
Test SMS confirmation to caller ID.
Measure phone latency separately from WebRTC latency.
```

## What Should Not Be Done Yet

Avoid these until v0.2 is reliable:

```text
Adding many new providers
Building a SaaS onboarding portal
Adding a full CRM suite
Advertising publicly
Selling phone production without SIP
Calling placeholder integrations "done"
Optimizing average latency while p95/tool truth is broken
```

The risk is spreading engineering attention over too many surfaces before the current voice-agent loop is trustworthy.

## Advertising Readiness Gap

Verbatim should not be advertised as a client-ready service yet. The demo is promising, but the product is missing two core requirements for real buyers: production telephony and reliable external-action truth. Without SIP trunking or phone-number routing, businesses cannot actually deploy it as their public call channel. And while the voice agent can sound good, it is still hit-or-miss: some calls have strong latency and useful conversation, but others include false booking/SMS claims, wrong tool behavior, high p95 latency, or persona drift. Before advertising, Verbatim needs a hardened tool-state system, separate normal/tool latency reporting, repeatable 100-call evaluations per bot version, and a working SIP path with caller-ID based SMS confirmation. Once those are in place, the service can be marketed as a real business voice agent rather than a fragile demo.

