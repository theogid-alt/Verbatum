# Verbatum Context

Verbatum is a no-code voice agent SaaS.

Goal:
Build a platform where businesses can create AI voice agents for sales, support, appointment booking, and lead qualification.

Current strategic direction:
- English-first MVP.
- Arabic-English multilingual moat later.
- SaaS platform, not just agency/custom bots.
- Target users: agencies, SMBs, real estate, lead-gen companies, customer support teams.

Current voice stack:
- Transport / realtime: LiveKit
- STT: Deepgram Nova 3
- LLM: Groq-hosted Llama model, chosen mainly for latency
- TTS: Cartesia Sonic
- Previous tests:
  - Pipecat caused too many runtime errors.
  - Deepgram Flux was not solid enough, especially eager end-of-turn.
  - Gemini 2.5 Flash was more intelligent but slower.
  - Groq Llama is fast but less smart.

Current performance:
- End-to-end response latency is reportedly averaging 400–600ms.
- Priority is maintaining low latency without making the agent dumb.

Product priorities:
1. Stable browser-based voice agent demo.
2. Natural interruption / turn-taking.
3. Tool calling.
4. Calendar / CRM integrations.
5. Telephony.
6. Evals and call scoring.
7. Multi-tenant SaaS dashboard.
8. Templates redirecting to app.verbatum.ai.
9. Later: multilingual Arabic-English infrastructure.

Important product principle:
Do not over-engineer too early. Shipping a stable MVP matters more than theoretical architecture purity.

Code review priorities:
- Trace full audio path.
- Identify latency bottlenecks.
- Find unnecessary awaits, buffers, blocking calls, or serialization delays.
- Check LiveKit room/session lifecycle.
- Check STT endpointing behavior.
- Check LLM streaming and TTFT.
- Check TTS first-audio latency.
- Check whether architecture can evolve into SaaS.
- Do not rewrite everything unless necessary.
