# Manual Voice Test Protocol

Run this against the local browser test UI after starting the FastAPI server and the Pipecat bot.

## Setup

1. Start the server with `uv run uvicorn verbatim.server:app --reload --port 8000`.
2. Open `http://localhost:8000`.
3. Click `Create Room`, `Start Agent`, then `Join Call`.
4. Allow microphone access.

## 10-Turn Smoke Script

Use these 10 utterances in one call:

1. "Hi, can you hear me?"
2. "What can you help me with?"
3. "I want to book an appointment."
4. "Actually never mind, I have another question."
5. "Can you repeat that?"
6. "What are your business hours?"
7. "Please connect me to a human."
8. "My name is John and my phone number is 555-0123."
9. "Wait, stop."
10. "Goodbye."

## 30-Turn Demo Benchmark

Use this for the current demo-quality benchmark. Keep the stack fixed for the whole run:

```text
LiveKit + Nova-3 + Groq LLaMA 3.1 8B Instant + Cartesia Sonic-3
```

### Short Functional Turns

1. "Hi, can you hear me?"
2. "What's your name?"
3. "How are you today?"
4. "What can you help me with?"
5. "Can you say that again?"
6. "One sec."
7. "Actually, wait."
8. "Please slow down a little."
9. "Can you send it on WhatsApp?"
10. "Thanks."

### Natural Real-Estate Turns

11. "I saw an apartment on Bayut and the price was not listed."
12. "It looked nice, but I don't know the building name."
13. "I might rent, I might buy, I'm not sure yet."
14. "I don't really have a fixed budget in mind."
15. "I like Jumeirah, but I'm open."
16. "The price felt too high for that one."
17. "I'm considering something bigger if it feels right."
18. "I want something that feels quiet, not too busy."
19. "Could someone send me a few options?"
20. "I'd rather continue on WhatsApp."

### Long-Sentence Turns

21. "Hey, I saw a property online, but the listing did not show the price, and I wanted to know if you had anything similar but maybe not exactly in the same area."
22. "I'm not fully sure if I want an apartment or a villa, because part of me wants something easy and part of me wants more space."
23. "The budget is flexible, but I don't want to feel like I'm overpaying just because the listing looks fancy."
24. "I need to think about location, commute, and whether the place feels comfortable for family visits."
25. "I'm not ready to book anything yet, but I do want to understand what kind of options are realistic."

### Interruption And Recovery Turns

26. Start speaking over Alicia after half a second: "Wait, let me finish."
27. Interrupt a response with: "Actually, no."
28. Say a tiny sound like "uh" and then stay quiet.
29. Interrupt with a continuation: "But also, I forgot to mention parking."
30. "Okay, that's enough for now. Goodbye."

## Acceptance Check

After the call, run:

```bash
uv run python scripts/summarize_latency.py --events ./data/verbatim/events.jsonl --call-id <call_id>
```

Confirm:

- The agent joined the selected WebRTC room.
- Browser speech reached the agent.
- The agent responded with spoken Cartesia audio.
- Each user turn produced structured events.
- Any turn above 2000 ms has a visible slowest known stage.
- `real_p95_ms` and `clean_p95_ms` are visible in the dashboard terminal.
- `premature_assistant_start_count`, `user_utterance_split_count`, `voice_cutout_suspected_count`,
  and `form_pattern_failure_count` stay within the demo target.

For the internal acceptance benchmark, run at least 100 user turns over WebRTC and investigate
all turns above 2000 ms. Treat any unexplained turn above 3000 ms as a red flag.
