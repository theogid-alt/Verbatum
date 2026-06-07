# Verbatim Project Deep Dive And Updated Roadmap

Date: 2026-05-29  
Current app version: v0.3.5  
Current protected stack:

```text
LiveKit -> Deepgram Flux -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

## 1. Executive Summary

Verbatim has moved from a voice-pipeline experiment into a local operator kit for building and testing client-specific voice agents. The current system can run WebRTC calls, compare transports/providers, use persistent local prompts and KB, run Google Calendar and Twilio SMS tools, summarize calls, collect manual evaluations, and preserve working versions through Git tags.

The biggest achievement so far is that the core custom cascade is now usable:

```text
LiveKit transport
Deepgram Flux STT
Groq LLaMA 3.1 8B Instant LLM
Cartesia Sonic-3 TTS
```

The biggest remaining gap is not whether the agent can speak. It can. The real gap is whether it can be trusted across many calls, many caller styles, and real business workflows. The current product is promising but not yet advertising-ready because it still lacks real telephony/SIP deployment, a large enough evaluation sample, production-grade tool reliability across industries, and a repeatable sales/demo funnel.

The roadmap has changed from a purely technical May to September engineering roadmap into a more product-shaped path:

```text
1. Evaluations
2. Telephony tests + branding/misc in parallel
3. Ads/sales pipeline + proof-of-concept/tool expansion in parallel
4. Self-serve onboarding/setup links
5. Semi-self-serve platform with 24/7 human support
6. Full self-serve voice-agent platform
```

That is the right shift. The project now needs proof, packaging, and repeatability more than random provider experimentation.

## 2. Current Scope

### What Verbatim Is Right Now

Verbatim is currently a cloneable local client kit. Each cloned folder can become one client voice-agent instance. The operator can edit:

```text
client/profile.json
client/prompt.md
client/kb.md
client/integrations.json
.env
```

The dashboard lets the operator:

```text
select LiveKit / Daily / Hume
select STT provider
select LLM provider
edit client profile
edit system prompt
edit persistent KB
connect/test integrations
start and stop calls
watch transcript and terminal events
review latency
save evaluations by bot version
dictate evaluation notes
```

This is intentionally not a SaaS yet. The current model is:

```text
clone repo
configure locally for a client
test calls locally
eventually connect to a phone number/SIP route
hand the client the phone number
```

### What Verbatim Is Not Yet

Verbatim is not yet:

```text
a hosted multi-client platform
a self-serve onboarding app
a production telephony product
a full integration marketplace
a fully automated evaluator
a CRM/listing system
a 24/7 support operation
```

Those are future layers. The immediate product is still a high-quality demo/proof-of-concept engine.

## 3. Current Architecture

### Runtime Modes

The v2/v0.3.5 app supports:

```text
1. Pipecat + LiveKit custom cascade
2. Pipecat + Daily custom cascade
3. Hume EVI direct comparison
```

The protected custom stack is:

```text
LiveKit -> Deepgram Flux -> Groq LLaMA 3.1 8B Instant -> Cartesia Sonic-3
```

Daily remains useful for comparison, but it has shown worse transport behavior in local tests. Hume remains useful as a native emotional voice-agent comparison, but the custom Pipecat cascade remains the main controllable baseline.

### Pipeline Shape

The Pipecat cascade is roughly:

```text
transport.input()
-> input probe
-> STT
-> STT probe
-> user context aggregator
-> direct tool/action gate
-> LLM
-> LLM probe
-> identity/tool-claim guard
-> TTS
-> TTS probe
-> transport.output()
-> output probe
-> assistant context aggregator
```

The most important architecture fix was per-call worker isolation:

```text
FastAPI server
-> starts one agent worker process per call
-> worker owns one transport/STT/LLM/TTS pipeline
-> one call_id maps to one active worker
-> separate call_ids can run concurrently up to the configured cap
```

This reduced the weird state contamination and SDK conflicts that happened when Daily, LiveKit, and different providers lived inside one long-running process.

### Local Data And Logs

Core v2 paths:

```text
data/verbatim/events_v2_clean.jsonl
data/verbatim/transcripts_v2_clean/
data/verbatim/calls_v2_clean/
data/verbatim/evaluations/{bot_version}/{call_id}.json
client/evaluation_rubric.json
```

This gives us local reproducibility without adding a hosted backend too early.

## 4. Current Capabilities

### Voice

Working:

```text
LiveKit WebRTC calls
Daily comparison calls
Hume comparison calls
Deepgram Nova-3 and Flux STT options
Groq/Gemini/OpenAI/Qwen/xAI/Mock LLM options
Cartesia Sonic-3 TTS
provider/model selectors
latency dashboard
transcript view
terminal log
one isolated worker per active call
```

Current winner:

```text
LiveKit + Flux + Groq + Sonic-3
```

### Client Kit

Working:

```text
local client profile editor
local system prompt editor
persistent KB editor
reset to baseline
integration card grid
saved local integration state
```

This supports the near-term business process: manually clone and configure a bot per client.

### Tool Calling

Working or partially working:

```text
Google Calendar availability through Nango
Google Calendar conflict checks
prepare viewing booking
confirm viewing booking
cancel Verbatim-created bookings
Twilio SMS follow-up
property detail SMS
property address SMS
booking confirmation SMS
tool terminal events
```

Current policy:

```text
read tools may run directly
calendar writes require confirmation
SMS sends only to trusted caller/session phone
external secrets are not exposed to the browser
raw provider tool catalogs are not exposed to the LLM
```

This is the right foundation. The LLM should see Verbatim-owned capabilities, not raw Google Calendar, Twilio, CRM, or automation APIs.

### Evaluation

Working:

```text
manual post-call scorecard
versioned evaluation folders
domain scores
review notes
auto metrics when available
browser dictation for notes
summary grouped by bot version
```

Current rubric:

```text
realism
tool_calling
latency
stt
intelligence
task_success
conversation_flow
faithfulness_safety
```

This is enough for human review, but not yet enough for professional benchmarking.

## 5. Evaluation Snapshot

Saved local evaluation reports currently total:

```text
45 evaluations across all saved versions
```

Version breakdown:

| Version | Saved evals | Overall avg |
|---|---:|---:|
| v01 | 10 | 3.20 |
| v02 | 9 | 3.37 |
| v02.2 | 5 | 3.19 |
| v02.3 | 11 | 3.47 |
| v0.3 | 5 | 3.70 |
| v0.3.1 | 5 | 3.29 |

Important interpretation:

```text
45 total historical evaluations is useful for direction.
It is not enough to prove the current version.
The next target is iterative testing: keep fixing repeated obvious failures every few calls, then require 30 stable calls above 4.0 average before selling.
```

The most recent evaluated versions show the core issue clearly:

```text
conversation flow and realism improved
latency is often acceptable
tool calling and faithfulness still create trust failures
```

For example, v0.3.1 had:

```text
5 evaluations
overall avg: 3.29
tool calling avg: 2.50
faithfulness/safety avg: 2.80
task success avg: 2.80
```

This is why v0.3.2 focused on small tool/truth fixes rather than changing the voice stack. v0.3.3 changed the call lifecycle so separate calls can run concurrently without changing the winning voice stack. v0.3.4 focused on calendar/SMS truth: next-week routing, split booking requests, safer default viewing slots, and longer tool timeouts for calendar reads. v0.3.5 adds a tool transaction ledger plus stricter booking/SMS truth gates for vague property context, unsupported calendar reads, and unusual agent/buyer inquiries.

## 6. Major Issues Encountered

### 1. Transport Instability And Cutouts

Earlier testing had repeated cutouts, frozen agents, disconnected dashboards, stale bots, and confusing behavior between Daily and LiveKit. Some of this was network-related, but a lot was local architecture complexity and mixed SDK state.

What helped:

```text
clean v2 reset
one isolated worker per active call
detached server scripts
per-call worker processes
LiveKit as main custom transport
browser/network stats
keeping Daily as comparison only
```

Current status:

```text
mostly stabilized for WebRTC demos
not yet proven on phone/SIP
```

### 2. STT And Turn Taking

The project bounced between Nova-3 and Flux. Nova was stable and initially lower-latency, while Flux only became useful once the full LiveKit stack stabilized. Early aggressive endpointing caused the agent to interrupt the user mid-sentence. More conservative settings increased latency.

The current lesson:

```text
STT is not just transcription.
STT is turn policy.
Too aggressive feels rude.
Too slow kills the demo.
```

Current winner:

```text
Flux in the LiveKit/Groq/Sonic-3 stack
```

Important constraint:

```text
Do not add alias handling casually.
Domain/STT errors should mostly be handled by better KB, business location, and evaluation notes unless repeated enough to justify a rule.
```

### 3. LLM Intelligence Versus Latency

The project tested Gemini, Groq, OpenAI, Qwen, xAI/Grok, UltraVox, Hume, and Mock paths. The repeated tradeoff was:

```text
faster models can be dumb/form-like
smarter models often introduce latency or provider spikes
native voice models can feel good but reduce control/observability
```

Groq LLaMA 3.1 8B Instant became the best custom-cascade compromise because it was fast enough and promptable enough.

Recurring LLM problems:

```text
form-filling behavior
repeating the caller's words
claiming a city/company/persona that was not provided
blocking simple questions behind qualification questions
pretending to know property information
lying about tools
asking to book too aggressively
```

What helped:

```text
short prompt
answer-first instruction
do not repeat caller wording
one follow-up question maximum
tool-result based direct responses
identity/tool-claim guard
manual evaluation feedback loop
```

### 4. TTS And Voice Quality

Cartesia Sonic-3 has remained the best stable TTS choice. TTS was rarely the main bottleneck compared to turn detection, LLM behavior, tool waits, or transport instability.

Current status:

```text
keep Cartesia Sonic-3
do not change TTS unless benchmarking specifically shows a p95 or cutout problem
```

### 5. Tool Calling Truthfulness

This has been the most serious product issue.

Observed failures:

```text
agent said it booked when it had not
agent said it sent SMS when it had not
agent said SMS was unavailable when the flow was wrong
agent pushed booking before checking enough context
agent asked for confirmation after already booking
agent could not generalize SMS beyond booking confirmations
agent sent raw KB/JSON-like property details by SMS
```

What improved:

```text
tool terminal events
booking confirmation guards
busy-slot checks
SMS property details
SMS address/booking context
no double-booking guards
v0.3.2 do-not-book guard
v0.3.2 cleaner property SMS formatting
```

Remaining direction:

```text
tools must be more capability-based and less flow-specific
the agent should be able to send property info, send address, check calendar, and book independently
every external action must be truth-based
tool failures must produce short honest fallback speech
```

### 6. Prompt Drift And Persona Bleed

The agent repeatedly kept old identity/location/persona assumptions after prompt changes. Dubai/CRTG/Alicia bleed was especially visible before the clean v2 reset.

What helped:

```text
client/prompt.md as the active local prompt
reset-to-baseline
shorter prompt
removing hardcoded company/city/name claims from defaults
identity bleed guard
```

Current status:

```text
much cleaner than before
still needs careful evaluation any time prompt/profile/KB changes
```

### 7. Evaluation Was Too Small And Too Ad Hoc

The manual evaluation layer now exists, but the sample is still small and mixed across versions/providers/prompts.

Current risk:

```text
we may fix one visible issue and accidentally regress another
```

Required next step:

```text
keep testing iteratively
fix obvious repeated failures as soon as they appear
separate normal turns from tool-heavy turns
track repeated issues only
ignore one-off outliers unless severe
graduate once one candidate reaches 30 stable calls above 4.0 average
```

## 7. Updated Roadmap From Here

### Phase 1: Evaluations

Goal:

```text
build enough evaluation evidence to know what is repeated, what is noise, and what blocks selling
```

This is the immediate priority. We should not wait for a supposedly stable version before testing, because testing is how the obvious issues surface. The practical loop is:

```text
run about 5 calls
fix obvious repeated or severe issues
version the change
repeat
```

Once a candidate can survive 30 stable calls with an average score above 4.0 and no repeated trust-breaking issues, it can move toward selling.

Recommended structure:

```text
20 normal real-estate inquiry calls
15 property-detail / KB calls
15 tool-heavy calls
10 stress calls with long utterances, corrections, endings, and edge cases
```

Score:

```text
realism
tool_calling
latency
stt
intelligence
task_success
conversation_flow
faithfulness_safety
```

Track separately:

```text
normal-turn latency
tool-turn latency
false tool claims
booking success
SMS success
STT issue that changed outcome
conversation ending quality
```

Success gate before moving hard into sales:

```text
30 stable calls on the same candidate
overall average above 4.0
no repeated false booking/SMS claims
no repeated catastrophic STT issue
tool calling average near or above 4.0
faithfulness/safety average near or above 4.0
normal-turn latency remains demo-quality
```

### Phase 2A: Telephony Tests With PBX And SIP

This should run simultaneously with evaluations.

Goal:

```text
understand whether the WebRTC stack survives real phone routing
```

Topics to deep dive:

```text
SIP trunks
PBX basics
Asterisk / FreePBX
Twilio Elastic SIP / Voice
Telnyx SIP / Voice
LiveKit SIP ingress/egress options
audio codecs: PCMU, PCMA, Opus
sample rates and transcoding
jitter buffers
DTMF / IVR
call transfer to human
call recording policy
caller ID
concurrent calls
failover to human
```

Key risk:

```text
WebRTC demo latency does not automatically translate to SIP/phone latency.
Phone audio adds codec, carrier, PBX, and routing overhead.
```

Recommended telephony proof order:

```text
1. local SIP/PBX learning lab
2. one inbound test number
3. one SIP-to-LiveKit or SIP-to-agent path
4. measure latency and audio quality
5. add human transfer
6. only then think about real client numbers
```

### Phase 2B: Branding And Misc

This should run simultaneously with evaluations.

Goal:

```text
make Verbatim look sellable while the product is still being validated
```

Deliverables:

```text
logo
basic landing page
short teaser clips
before/after demo videos
one-page sales PDF
simple product narrative
demo script
client objection answers
```

Brand positioning:

```text
not generic chatbot
not call center replacement yet
fast voice agents for business calls
human-like enough for demos
integration-ready for real workflows
```

### Phase 3A: Ads And Sales Pipeline

This should start after enough evaluation confidence exists and branding is coherent.

Goal:

```text
test whether businesses want this before building a full SaaS
```

Sales pipeline should include:

```text
ICP definition
lead source
landing page
demo booking
qualification
free trial or paid pilot offer
onboarding checklist
client test criteria
deployment handoff
support process
```

Do not advertise heavily before:

```text
telephony path works
evaluation results are acceptable
tool truthfulness is stable
demo script is repeatable
```

### Phase 3B: Proof Of Concept + Tool Calling Expansion

This should run alongside sales learning.

Goal:

```text
serve more industries without custom-coding each bot from scratch
```

The right abstraction is:

```text
industry template
business profile
KB
integration cards
Verbatim-owned tool capabilities
tool policies
evaluation rubric
```

Do not expose raw app APIs to the LLM. Add industry-safe capabilities:

```text
Real estate:
search/list property info
book viewing
send property SMS
create lead

Clinics:
check appointment availability
book consultation
send intake link
route urgent cases

Restaurants:
reservation check
booking
opening hours
special requests

Home services:
qualify job
book estimate
send quote follow-up
create CRM lead
```

First expansion targets should be industries with:

```text
simple calls
clear booking/follow-up actions
low regulatory risk
high missed-call cost
simple integrations
```

### Phase 4: Self-Serve Onboarding / Setup Links

This is later, not now.

Goal:

```text
auto-program a basic voice agent from a form
```

User flow:

```text
client opens onboarding link
chooses industry
enters business basics
uploads/pastes KB
chooses voice/persona
connects integrations
reviews allowed actions
gets a test call link
```

Output:

```text
client profile
prompt
KB
enabled tools
integration connections
evaluation template
deployment checklist
```

### Phase 5: Semi-Self-Serve Platform + 24/7 Human Support

Goal:

```text
clients can configure common things, but Verbatim still helps with deployment and support
```

Needed:

```text
hosted dashboard
client auth
integration management
call logs
support tickets
human review
deployment status
billing/admin basics
```

This is probably the first commercially realistic platform stage.

### Phase 6: Full Self-Serve Voice-Agent Platform

Goal:

```text
businesses can create, connect, test, deploy, monitor, and improve agents without Verbatim manually configuring every client
```

Needed:

```text
multi-tenant backend
secure secrets vault
hosted worker pool
telephony provisioning
integration marketplace
automated evals
prompt/KB/version management
analytics
billing
support workflows
compliance controls
```

This should only be built after:

```text
manual onboarding works repeatedly
sales pipeline proves demand
telephony works reliably
tool integrations are stable
support burden is understood
```

## 8. Strategic Priorities

### Priority 1: Protect The Winning Stack

Do not casually change:

```text
LiveKit
Flux
Groq LLaMA 3.1 8B Instant
Cartesia Sonic-3
worker isolation
short prompt
one isolated worker per active call
tool terminal telemetry
```

Provider experiments should happen as separate versioned comparisons, not by mutating the protected baseline.

### Priority 2: Make Evaluation Serious

The next evaluation loop should become the product decision engine: short batches reveal obvious issues, and a 30-call stable run above 4.0 average becomes the selling gate.

Important rule:

```text
Only fix repeated issues.
Do not chase one-off weirdness unless it is severe, unsafe, or embarrassing.
```

### Priority 3: Tool Truth Over Tool Quantity

It is better to have:

```text
4 tools that never lie
```

than:

```text
20 tools that sometimes pretend to work
```

Every tool needs:

```text
clear trigger
safe confirmation policy
truthful response formatter
terminal event
evaluation signal
timeout fallback
```

### Priority 4: Telephony Before Ads

Advertising before telephony is risky because the current demo is WebRTC. Most customers will care about:

```text
real phone number
inbound calls
reliable routing
human transfer
call logs
SMS/WhatsApp follow-up
```

The sales website can be built early, but paid acquisition should wait until the phone path is proven enough not to embarrass the offer.

## 9. What Is Missing Before Advertising

Verbatim should not be advertised as a ready business phone agent yet. The product is missing a reliable telephony/SIP path, enough version-specific evaluations to prove quality, stronger tool truthfulness around bookings and follow-ups, repeatable client setup packaging, and a clear support/deployment process. The core demo stack is now promising, but advertising too early would create sales pressure before the agent can reliably handle real phone calls, real client integrations, and real customer expectations. The next milestone is not more random capability; it is proof: iterative evaluation batches, then 30 stable calls above 4.0 average on one candidate, a working SIP/PBX test path, a polished demo/brand package, and tool calling that is boringly truthful.
