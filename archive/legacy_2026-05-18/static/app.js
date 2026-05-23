const state = {
  transportProvider: "daily",
  dailyGeo: null,
  roomUrl: "",
  roomToken: null,
  roomName: null,
  callId: null,
  sessionId: null,
  callFrame: null,
  livekitRoom: null,
  livekitAudioEls: [],
  livekitRemoteAudioTracks: [],
  livekitAudioUnlocked: false,
  livekitStatsTimer: null,
  livekitLastStats: null,
  metricsTimer: null,
  sttProvider: "deepgram",
  deepgramModel: "nova-3-general",
  llmProvider: "gemini",
  llmModel: "gemini-2.5-flash",
  llmOptions: [],
  livekitAudioInSampleRate: null,
  livekitAudioOutSampleRate: null,
  livekitAudioOutBitrate: 96000,
  livekitAudioOut10msChunks: 4,
  livekitAudioOutAutoSilence: true,
  livekitBrowserEchoCancellation: true,
  livekitBrowserNoiseSuppression: true,
  livekitBrowserAutoGainControl: true,
  livekitBrowserAudioSampleRate: 48000,
  humeSession: null,
  humeSocket: null,
  humeRecorder: null,
  humeMicStream: null,
  humeAudioQueue: [],
  humeCurrentAudio: null,
  humeAudioPlaying: false,
  humeFirstAudioAt: null,
  humeFirstAudioPlayingAt: null,
  humeLastUserMessageAt: null,
  humeLastAssistantAudioAt: null,
  humeRecentMessages: {},
  latencyDiagnosticMode: true,
  callHasStarted: false,
  agentRunning: false,
};

const LLM_PROVIDER_STORAGE_KEY = "verbatim.llmProvider";

const statusEl = document.querySelector("#status");
const logEl = document.querySelector("#log");
const roomUrlEl = document.querySelector("#roomUrl");
const roomUrlLabelEl = document.querySelector("#roomUrlLabel");
const prepareButton = document.querySelector("#prepareButton");
const startAgentButton = document.querySelector("#startAgentButton");
const joinButton = document.querySelector("#joinButton");
const openRoomButton = document.querySelector("#openRoomButton");
const leaveButton = document.querySelector("#leaveButton");
const killAgentButton = document.querySelector("#killAgentButton");
const dailyTransportButton = document.querySelector("#dailyTransportButton");
const livekitTransportButton = document.querySelector("#livekitTransportButton");
const humeTransportButton = document.querySelector("#humeTransportButton");
const transportCurrentEl = document.querySelector("#transportCurrent");
const dailyRegionAutoButton = document.querySelector("#dailyRegionAutoButton");
const dailyRegionFrankfurtButton = document.querySelector("#dailyRegionFrankfurtButton");
const dailyRegionLondonButton = document.querySelector("#dailyRegionLondonButton");
const dailyRegionCurrentEl = document.querySelector("#dailyRegionCurrent");
const fluxButton = document.querySelector("#fluxButton");
const novaButton = document.querySelector("#novaButton");
const engineCurrentEl = document.querySelector("#engineCurrent");
const geminiButton = document.querySelector("#geminiButton");
const groqButton = document.querySelector("#groqButton");
const openaiButton = document.querySelector("#openaiButton");
const qwenButton = document.querySelector("#qwenButton");
const xaiButton = document.querySelector("#xaiButton");
const ultravoxButton = document.querySelector("#ultravoxButton");
const mockLlmButton = document.querySelector("#mockLlmButton");
const llmCurrentEl = document.querySelector("#llmCurrent");
const diagnosticButton = document.querySelector("#diagnosticButton");
const diagnosticCurrentEl = document.querySelector("#diagnosticCurrent");
const callFrameEl = document.querySelector("#callFrame");
const metricsStatusEl = document.querySelector("#metricsStatus");
const botTerminalEl = document.querySelector("#botTerminal");
const latencyHealthEl = document.querySelector("#latencyHealth");
const latencyPerceivedEl = document.querySelector("#latencyPerceived");
const latencyP95El = document.querySelector("#latencyP95");
const latencyTranscriptPlaybackEl = document.querySelector("#latencyTranscriptPlayback");
const latencyTranscriptEnqueueEl = document.querySelector("#latencyTranscriptEnqueue");
const latencyTurnDetectionEl = document.querySelector("#latencyTurnDetection");
const latencyLlmTtftEl = document.querySelector("#latencyLlmTtft");
const latencyProviderTtfbEl = document.querySelector("#latencyProviderTtfb");
const latencyTtsAudioEl = document.querySelector("#latencyTtsAudio");
const latencyCleanP95El = document.querySelector("#latencyCleanP95");
const latencyInterruptionsEl = document.querySelector("#latencyInterruptions");
const latencyTurnQualityEl = document.querySelector("#latencyTurnQuality");
const latencyFormFailuresEl = document.querySelector("#latencyFormFailures");
const latencyModelEl = document.querySelector("#latencyModel");
const latencyCallEl = document.querySelector("#latencyCall");
const transcriptStatusEl = document.querySelector("#transcriptStatus");
const transcriptFeedEl = document.querySelector("#transcriptFeed");
const sttEventsEl = document.querySelector("#sttEvents");

function setStatus(text) {
  statusEl.textContent = text;
}

function log(message, data) {
  const suffix = data ? ` ${JSON.stringify(data)}` : "";
  logEl.textContent = `${new Date().toLocaleTimeString()} ${message}${suffix}\n${logEl.textContent}`;
}

function sendClientEvent(eventName, metadata = {}) {
  if (!state.callId) {
    return;
  }
  fetch("/api/analytics/client-event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      call_id: state.callId,
      session_id: state.sessionId,
      event_name: eventName,
      provider: "browser",
      metadata: {
        transport_provider: state.transportProvider,
        room_name: state.roomName,
        ...metadata,
      },
    }),
  }).catch((error) => {
    log("Client telemetry failed", { error_message: error.message });
  });
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function currentRoomUrl() {
  return roomUrlEl.value || state.roomUrl;
}

function transportLabel(provider) {
  if (provider === "hume_evi") {
    return "Hume EVI";
  }
  return provider === "livekit" ? "LiveKit" : "Daily";
}

function setTransport(provider) {
  state.transportProvider =
    provider === "hume_evi" ? "hume_evi" : provider === "livekit" ? "livekit" : "daily";
  dailyTransportButton.classList.toggle("active", state.transportProvider === "daily");
  livekitTransportButton.classList.toggle("active", state.transportProvider === "livekit");
  humeTransportButton.classList.toggle("active", state.transportProvider === "hume_evi");
  dailyTransportButton.setAttribute("aria-pressed", String(state.transportProvider === "daily"));
  livekitTransportButton.setAttribute("aria-pressed", String(state.transportProvider === "livekit"));
  humeTransportButton.setAttribute("aria-pressed", String(state.transportProvider === "hume_evi"));
  transportCurrentEl.textContent = transportLabel(state.transportProvider);
  roomUrlLabelEl.textContent =
    state.transportProvider === "hume_evi"
      ? "Hume endpoint"
      : state.transportProvider === "livekit"
        ? "LiveKit URL"
        : "Daily room";
  roomUrlEl.placeholder =
    state.transportProvider === "hume_evi"
      ? "wss://api.hume.ai/v0/evi/chat"
      : state.transportProvider === "livekit"
        ? "wss://your-project.livekit.cloud"
        : "Daily room URL";
  openRoomButton.textContent =
    state.transportProvider === "hume_evi"
      ? "Open EVI"
      : state.transportProvider === "livekit"
        ? "Open Room"
        : "Open Daily Room";
  openRoomButton.disabled = state.transportProvider !== "daily" || !state.roomUrl;
}

function dailyRegionLabel(geo) {
  if (geo === "eu-central-1") {
    return "Frankfurt · eu-central-1";
  }
  if (geo === "eu-west-2") {
    return "London · eu-west-2";
  }
  return "Auto · provider selected";
}

function setDailyRegion(geo) {
  state.dailyGeo = geo || null;
  dailyRegionAutoButton.classList.toggle("active", !state.dailyGeo);
  dailyRegionFrankfurtButton.classList.toggle("active", state.dailyGeo === "eu-central-1");
  dailyRegionLondonButton.classList.toggle("active", state.dailyGeo === "eu-west-2");
  dailyRegionAutoButton.setAttribute("aria-pressed", String(!state.dailyGeo));
  dailyRegionFrankfurtButton.setAttribute(
    "aria-pressed",
    String(state.dailyGeo === "eu-central-1"),
  );
  dailyRegionLondonButton.setAttribute("aria-pressed", String(state.dailyGeo === "eu-west-2"));
  dailyRegionCurrentEl.textContent = dailyRegionLabel(state.dailyGeo);
}

function sttLabel(provider, model) {
  if (provider === "ultravox") {
    return `UltraVox · ${model || "audio-native"}`;
  }
  if (provider === "deepgram_flux") {
    return `Flux · ${model || "flux-general-en"}`;
  }
  if (model === "nova-3-general") {
    return "Nova-3 · nova-3-general";
  }
  return `Deepgram · ${model || "default"}`;
}

function setSttEngine(provider, model) {
  state.sttProvider = provider;
  state.deepgramModel = model;
  fluxButton.classList.toggle("active", provider === "deepgram_flux");
  novaButton.classList.toggle("active", provider === "deepgram" && model === "nova-3-general");
  fluxButton.setAttribute("aria-pressed", String(provider === "deepgram_flux"));
  novaButton.setAttribute("aria-pressed", String(provider === "deepgram" && model === "nova-3-general"));
  engineCurrentEl.textContent = sttLabel(provider, model);
}

function llmLabel(provider, model) {
  if (provider === "openai") {
    return `OpenAI · ${model || "gpt-4o-mini"}`;
  }
  if (provider === "groq") {
    return `Groq · ${model || "llama-3.1-8b-instant"}`;
  }
  if (provider === "qwen") {
    return `Qwen · ${model || optionForProvider("qwen")?.llm_model || "qwen3.5-flash"}`;
  }
  if (provider === "xai") {
    return `xAI · ${model || "grok-4-1-fast-non-reasoning"}`;
  }
  if (provider === "ultravox") {
    return `UltraVox · ${model || "fixie-ai/ultravox"}`;
  }
  if (provider === "hume_evi") {
    return `Hume EVI · ${model || "speech-to-speech"}`;
  }
  if (provider === "mock") {
    return "Mock · immediate";
  }
  return `Gemini · ${model || "gemini-2.5-flash"}`;
}

function loadSavedLlmProvider() {
  try {
    return window.localStorage.getItem(LLM_PROVIDER_STORAGE_KEY);
  } catch (error) {
    return null;
  }
}

function saveLlmProvider(provider) {
  try {
    window.localStorage.setItem(LLM_PROVIDER_STORAGE_KEY, provider);
  } catch (error) {
    // localStorage can be unavailable in private or restricted browser contexts.
  }
}

function knownLlmProvider(provider) {
  return ["gemini", "groq", "openai", "qwen", "xai", "ultravox", "mock"].includes(provider);
}

function defaultModelForProvider(provider, fallbackModel = null) {
  const optionModel = optionForProvider(provider)?.llm_model;
  if (optionModel) {
    return optionModel;
  }
  if (fallbackModel) {
    return fallbackModel;
  }
  if (provider === "groq") {
    return "llama-3.1-8b-instant";
  }
  if (provider === "openai") {
    return "gpt-4o-mini";
  }
  if (provider === "qwen") {
    return "qwen3.5-flash";
  }
  if (provider === "xai") {
    return "grok-4-1-fast-non-reasoning";
  }
  if (provider === "ultravox") {
    return "fixie-ai/ultravox";
  }
  if (provider === "mock") {
    return "mock-immediate";
  }
  return "gemini-2.5-flash";
}

function setLlmEngine(provider, model, options = {}) {
  const selectedProvider = knownLlmProvider(provider) ? provider : "gemini";
  const selectedModel = model || defaultModelForProvider(selectedProvider);
  const shouldPersist = options.persist !== false;
  state.llmProvider = selectedProvider;
  state.llmModel = selectedModel;
  geminiButton.classList.toggle("active", selectedProvider === "gemini");
  groqButton.classList.toggle("active", selectedProvider === "groq");
  openaiButton.classList.toggle("active", selectedProvider === "openai");
  qwenButton.classList.toggle("active", selectedProvider === "qwen");
  xaiButton.classList.toggle("active", selectedProvider === "xai");
  ultravoxButton.classList.toggle("active", selectedProvider === "ultravox");
  mockLlmButton.classList.toggle("active", selectedProvider === "mock");
  geminiButton.setAttribute("aria-pressed", String(selectedProvider === "gemini"));
  groqButton.setAttribute("aria-pressed", String(selectedProvider === "groq"));
  openaiButton.setAttribute("aria-pressed", String(selectedProvider === "openai"));
  qwenButton.setAttribute("aria-pressed", String(selectedProvider === "qwen"));
  xaiButton.setAttribute("aria-pressed", String(selectedProvider === "xai"));
  ultravoxButton.setAttribute("aria-pressed", String(selectedProvider === "ultravox"));
  mockLlmButton.setAttribute("aria-pressed", String(selectedProvider === "mock"));
  llmCurrentEl.textContent = llmLabel(selectedProvider, selectedModel);
  if (shouldPersist) {
    saveLlmProvider(selectedProvider);
  }
}

function optionForProvider(provider) {
  return (state.llmOptions || []).find((option) => option.llm_provider === provider);
}

function describeDailyEvent(event) {
  if (!event) {
    return {};
  }
  return {
    action: event.action,
    errorMsg: event.errorMsg,
    error: event.error,
    type: event.type,
    participant: event.participant && {
      local: event.participant.local,
      owner: event.participant.owner,
      session_id: event.participant.session_id,
    },
  };
}

function formatMs(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return `${Math.round(Number(value))} ms`;
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return `${Number(value).toFixed(1)}%`;
}

function errorCount(errorsByProvider) {
  return Object.values(errorsByProvider || {}).reduce((total, count) => total + Number(count || 0), 0);
}

function shortTime(isoTimestamp) {
  if (!isoTimestamp) {
    return "";
  }
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.valueOf())) {
    return "";
  }
  return date.toLocaleTimeString();
}

function terminalTime(isoTimestamp) {
  return shortTime(isoTimestamp) || "--:--:--";
}

function truncate(value, maxLength = 140) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1)}…`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeMetadata(metadata = {}) {
  const allowedKeys = [
    "frame_type",
    "transport_provider",
    "room_name",
    "participant",
    "llm_provider",
    "llm_model",
    "llm_started_reason",
    "queue_depth",
    "old_llm_running",
    "active_llm_turn_id",
    "active_llm_cancelled",
    "barge_in_before_audio",
    "stale_llm_completed",
    "phantom_turn_prevented",
    "metric_type",
    "value",
    "source",
    "text_preview",
    "transcript",
    "error_type",
    "error_message",
    "outcome",
    "reason",
    "word_count",
    "fast_ack_used",
    "timeout_ms",
    "stage",
    "final",
    "is_final",
    "speech_final",
    "result_event",
    "result_speech_final",
    "result_is_final",
    "conversation_mode",
    "possible_barge_in",
    "valid_barge_in",
    "false_barge_in",
    "premature_assistant_start",
    "user_utterance_split",
    "voice_cutout_suspected",
    "assistant_speech_cancelled_reason",
    "resume_after_assistant_ms",
    "gap_ms",
    "message_type",
    "chat_id",
    "chat_group_id",
    "audio_queue_depth",
    "audio_output_count",
    "hume_latency_ms",
    "playback_delay_ms",
    "config_id",
    "config_version",
    "verbose_transcription",
    "audio_mime_type",
  ];
  return allowedKeys
    .filter((key) => metadata[key] !== undefined && metadata[key] !== null && metadata[key] !== "")
    .map((key) => `${key}=${truncate(metadata[key], key === "text_preview" || key === "transcript" ? 90 : 48)}`)
    .join(" ");
}

function terminalEventLine(event) {
  const provider = event.provider ? ` ${event.provider}` : "";
  const turn = event.turn_id ? ` ${event.turn_id}` : "";
  const metadata = safeMetadata(event.metadata || {});
  return `[${terminalTime(event.timestamp_wall_iso)}]${turn}${provider} ${event.event_name}${metadata ? ` | ${metadata}` : ""}`;
}

function slowTurnLine(turn) {
  const perceived = turn.latency?.perceived_response_latency_ms;
  const transcriptPlayback = turn.latency?.transcript_ready_to_playback_ms;
  const ultravoxResponse = turn.latency?.ultravox_response_latency_ms;
  const ultravoxProcessing = turn.latency?.ultravox_processing_latency_ms;
  const displayLatency = ultravoxResponse ?? ultravoxProcessing ?? transcriptPlayback ?? perceived;
  if (displayLatency === null || displayLatency === undefined) {
    return null;
  }
  return `[slow] ${turn.turn_id} real=${formatMs(displayLatency)} transcript=${formatMs(transcriptPlayback)} perceived=${formatMs(perceived)} bottleneck=${turn.dominant_bottleneck || "unknown"} stage=${turn.slowest_stage || "unknown"}`;
}

function turnSummaryLine(turn) {
  const perceived = turn.latency?.perceived_response_latency_ms;
  const transcriptPlayback = turn.latency?.transcript_ready_to_playback_ms;
  const ultravoxResponse = turn.latency?.ultravox_response_latency_ms;
  const ultravoxProcessing = turn.latency?.ultravox_processing_latency_ms;
  const displayLatency = ultravoxResponse ?? ultravoxProcessing ?? transcriptPlayback;
  const commitGap = turn.latency?.transcript_ready_to_llm_enqueue_ms;
  const flags = [
    turn.active_llm_cancelled ? "llm_cancelled" : "",
    turn.barge_in_before_audio ? "barge_before_audio" : "",
    turn.stale_llm_completed ? "stale_llm" : "",
    turn.phantom_turn_prevented ? "phantom_prevented" : "",
    turn.valid_barge_in ? "valid_barge" : "",
    turn.false_barge_in ? "false_barge" : "",
    turn.premature_assistant_start ? "early_start" : "",
    turn.user_utterance_split ? "split" : "",
    turn.voice_cutout_suspected ? "cutout?" : "",
    turn.form_pattern_detected ? "form" : "",
  ]
    .filter(Boolean)
    .join(",");
  const mode = turn.conversation_mode ? ` mode=${turn.conversation_mode}` : "";
  return `[turn] ${turn.turn_id} outcome=${turn.outcome || "unknown"}${mode} real=${formatMs(displayLatency)} perceived=${formatMs(perceived)} commit_gap=${formatMs(commitGap)} slowest=${turn.slowest_stage || "unknown"} bottleneck=${turn.dominant_bottleneck || "unknown"}${flags ? ` flags=${flags}` : ""}`;
}

function renderDiagnosticMode(config = {}) {
  const enabled = config.latency_diagnostic_mode !== false;
  state.latencyDiagnosticMode = enabled;
  diagnosticButton.classList.toggle("active", enabled);
  diagnosticButton.setAttribute("aria-pressed", String(enabled));
  const history = config.llm_history_messages ?? 2;
  const maxTokens = config.llm_max_tokens ?? 32;
  const stopTimeout = config.user_turn_stop_timeout ?? 5;
  const echo = config.echo_suppression_ms ?? 0;
  const commit = config.final_transcript_eager_commit !== false;
  const muted = config.mute_user_while_bot_speaking !== false;
  const firstPhrase = config.tts_first_phrase_flush_enabled ? "phrase" : "sentence";
  const bufferDelay = config.cartesia_max_buffer_delay_ms ?? "default";
  diagnosticCurrentEl.textContent = enabled
    ? `on · history ${history} · ${maxTokens} tokens · ${stopTimeout}s safety · commit ${commit ? "final" : "user-stop"} · ${muted ? "bot-mute" : "barge"} · ${firstPhrase} · buffer ${bufferDelay} · ${echo}ms echo`
    : "off";
}

function setLatencyHealth(perceivedMs, activeAgents) {
  latencyHealthEl.classList.remove("good", "warn", "slow");
  if (!activeAgents) {
    latencyHealthEl.textContent = "Idle";
    return;
  }
  if (perceivedMs === null || perceivedMs === undefined || Number.isNaN(Number(perceivedMs))) {
    latencyHealthEl.textContent = "Tracking";
    return;
  }
  const value = Number(perceivedMs);
  if (value <= 900) {
    latencyHealthEl.textContent = "Sharp";
    latencyHealthEl.classList.add("good");
  } else if (value <= 1800) {
    latencyHealthEl.textContent = "Watch";
    latencyHealthEl.classList.add("warn");
  } else {
    latencyHealthEl.textContent = "Slow";
    latencyHealthEl.classList.add("slow");
  }
}

function renderLatencyPanel(summary, providerTtfb, ttsTtfb) {
  const llmProvider = summary.llm_provider || state.llmProvider;
  const llmModel = summary.llm_model || state.llmModel;
  const transportProvider = summary.transport_provider || state.transportProvider;
  const activeAgents =
    Number(summary.active_agents || 0) ||
    (transportProvider === "hume_evi" && state.humeSocket ? 1 : 0);
  const llmTtft = summary.avg_llm_ttft_total_ms ?? providerTtfb;
  const isUltravox = llmProvider === "ultravox";
  const realPath = isUltravox
    ? summary.avg_ultravox_response_latency_ms ??
      summary.avg_ultravox_processing_latency_ms ??
      summary.avg_transcript_ready_to_playback_ms
    : transportProvider === "hume_evi"
      ? summary.avg_hume_first_audio_playing_ms ?? summary.avg_transcript_ready_to_playback_ms
    : summary.avg_transcript_ready_to_playback_ms;
  const realPathP95 = isUltravox
    ? summary.p95_ultravox_response_latency_ms ??
      summary.p95_ultravox_processing_latency_ms ??
      summary.p95_transcript_ready_to_playback_ms
    : transportProvider === "hume_evi"
      ? summary.p95_hume_first_audio_playing_ms ?? summary.p95_transcript_ready_to_playback_ms
    : summary.p95_transcript_ready_to_playback_ms;
  const perceivedDisplay = summary.avg_perceived_latency_ms ?? realPath;
  latencyPerceivedEl.textContent = formatMs(perceivedDisplay);
  latencyP95El.textContent = formatMs(realPathP95 ?? summary.p95_perceived_latency_ms);
  latencyTranscriptPlaybackEl.textContent = formatMs(realPath);
  latencyTranscriptEnqueueEl.textContent = formatMs(
    summary.avg_transcript_ready_to_llm_enqueue_ms ?? summary.avg_transcript_to_llm_enqueue_ms
  );
  latencyTurnDetectionEl.textContent = formatMs(summary.avg_turn_detection_latency_ms);
  latencyLlmTtftEl.textContent = formatMs(llmTtft);
  latencyProviderTtfbEl.textContent = formatMs(providerTtfb);
  latencyTtsAudioEl.textContent = formatMs(ttsTtfb);
  latencyCleanP95El.textContent = formatMs(
    summary.clean_p95_ms ?? summary.clean_p95_transcript_ready_to_playback_ms
  );
  latencyInterruptionsEl.textContent = `${summary.interrupted_turns || 0} / ${summary.valid_barge_in_count || 0}`;
  latencyTurnQualityEl.textContent = `${summary.user_utterance_split_count || 0} / ${summary.premature_assistant_start_count || 0}`;
  latencyFormFailuresEl.textContent = `${summary.form_pattern_failure_count || 0} / ${summary.style_guard_rewrite_count || 0}`;
  latencyModelEl.textContent = llmLabel(llmProvider, llmModel);
  latencyCallEl.textContent = `call: ${summary.latest_call_id || state.callId || "none"} · ${transportLabel(transportProvider)} · diag ${summary.latency_diagnostic_mode === false ? "off" : "on"}`;
  setLatencyHealth(realPath ?? perceivedDisplay, activeAgents);
}

function renderBotTerminal(summary, providerTtfb, ttsTtfb) {
  const llmProvider = summary.llm_provider || state.llmProvider;
  const llmModel = summary.llm_model || state.llmModel;
  const transportProvider = summary.transport_provider || state.transportProvider;
  const ttsProvider = summary.tts_provider || (llmProvider === "ultravox" ? "ultravox" : "cartesia");
  const ttsLabel =
    ttsProvider === "hume_evi"
      ? "Hume EVI/direct"
      : ttsProvider === "ultravox"
      ? `UltraVox/${summary.tts_model || llmModel || "voice"}`
      : `Cartesia/${summary.tts_text_aggregation_mode || "sentence"}`;
  const livekitTransportLine =
    transportProvider === "livekit"
      ? `livekit chunks=${summary.livekit_audio_out_10ms_chunks ?? state.livekitAudioOut10msChunks}x10ms auto_silence=${summary.livekit_audio_out_auto_silence === false ? "off" : "on"} out_rate=${summary.livekit_audio_out_sample_rate ?? state.livekitAudioOutSampleRate ?? "default"} bitrate=${summary.livekit_audio_out_bitrate ?? state.livekitAudioOutBitrate} mic_echo=${summary.livekit_browser_echo_cancellation === false ? "off" : "on"} mic_noise=${summary.livekit_browser_noise_suppression === false ? "off" : "on"} agc=${summary.livekit_browser_auto_gain_control === false ? "off" : "on"}`
      : null;
  const clientStats = summary.livekit_client_stats || {};
  const clientEventCounts = summary.livekit_client_event_counts || {};
  const livekitClientLine =
    transportProvider === "livekit"
      ? `client net state=${clientStats.connection_state || "n/a"} quality=${clientStats.local_connection_quality || "n/a"} loss=${formatPct(clientStats.inbound_packet_loss_pct)} jitter=${formatMs(clientStats.jitter_ms)} rtt=${formatMs(clientStats.rtt_ms)} jitter_buffer=${formatMs(clientStats.jitter_buffer_delay_ms)} concealed=${clientStats.concealed_audio_samples ?? "n/a"} audio_wait=${clientEventCounts["browser.audio.waiting"] || 0} audio_stall=${clientEventCounts["browser.audio.stalled"] || 0} reconnects=${clientEventCounts["livekit.client.reconnecting"] || 0}/${clientEventCounts["livekit.client.reconnected"] || 0}`
      : null;
  const ultravoxLine =
    llmProvider === "ultravox"
      ? `ultravox vad endpoint=${summary.ultravox_turn_endpoint_delay_seconds ?? "default"}s min_turn=${summary.ultravox_minimum_turn_duration_seconds ?? "default"}s interrupt=${summary.ultravox_minimum_interruption_duration_seconds ?? "default"}s threshold=${summary.ultravox_frame_activation_threshold ?? "default"} buffer=${summary.ultravox_client_buffer_size_ms ?? "default"}ms idle=${summary.ultravox_media_idle_timeout_seconds ?? "default"}s response_avg=${formatMs(summary.avg_ultravox_response_latency_ms)} response_p95=${formatMs(summary.p95_ultravox_response_latency_ms)} full_avg=${formatMs(summary.avg_ultravox_processing_latency_ms)}`
      : null;
  const humeLine =
    transportProvider === "hume_evi" || llmProvider === "hume_evi"
      ? `hume evi direct config=${summary.hume_evi_config_id || "default"} version=${summary.hume_evi_config_version ?? "latest"} verbose=${summary.hume_evi_verbose_transcription === false ? "off" : "on"} prompt_session=${summary.hume_evi_send_system_prompt === false ? "off" : "on"} first_play=${formatMs(summary.avg_hume_first_audio_playing_ms)} p95=${formatMs(summary.p95_hume_first_audio_playing_ms)} output_to_play=${formatMs(summary.avg_hume_audio_output_to_playback_ms)} audio_out=${clientEventCounts["hume.client.audio_output"] || 0} interruptions=${clientEventCounts["hume.client.user_interruption"] || 0} playback_errors=${(clientEventCounts["hume.client.audio_playback_error"] || 0) + (clientEventCounts["hume.client.audio_autoplay_blocked"] || 0)}`
      : null;
  const contributors = (summary.p95_bottleneck_contributors || [])
    .slice(0, 4)
    .map((item) => `${item.bottleneck}:${item.percent}%`)
    .join(" ");
  const modeDistribution = Object.entries(summary.conversation_mode_counts || {})
    .slice(0, 5)
    .map(([mode, count]) => `${mode}:${count}`)
    .join(" ");
  const lines = [
    `verbatim bot terminal`,
    `call=${summary.latest_call_id || state.callId || "none"} transport=${transportLabel(transportProvider)} room=${summary.room_name || state.roomName || "n/a"} agent=${Number(summary.active_agents || 0) > 0 ? "running" : "idle"} turns=${summary.total_turns || 0} errors=${errorCount(summary.error_count_by_provider)}`,
    `stt="${sttLabel(summary.stt_provider || state.sttProvider, summary.stt_model || state.deepgramModel)}" llm="${llmLabel(llmProvider, llmModel)}" tts="${ttsLabel}" safety_timeout=${summary.user_turn_stop_timeout ?? "n/a"}s`,
    `latency real_avg=${formatMs(summary.avg_ultravox_response_latency_ms ?? summary.avg_ultravox_processing_latency_ms ?? summary.avg_hume_first_audio_playing_ms ?? summary.avg_transcript_ready_to_playback_ms)} real_p95=${formatMs(summary.p95_ultravox_response_latency_ms ?? summary.p95_ultravox_processing_latency_ms ?? summary.p95_hume_first_audio_playing_ms ?? summary.p95_transcript_ready_to_playback_ms)} perceived_avg=${formatMs(summary.avg_perceived_latency_ms ?? summary.avg_transcript_ready_to_playback_ms)} perceived_p95=${formatMs(summary.p95_perceived_latency_ms ?? summary.p95_transcript_ready_to_playback_ms)} source=${summary.perceived_latency_source || "n/a"}`,
    `stages commit_gap=${formatMs(summary.avg_transcript_ready_to_llm_enqueue_ms ?? summary.avg_transcript_to_llm_enqueue_ms)} turn_detection=${formatMs(summary.avg_turn_detection_latency_ms)} llm_ttft=${formatMs(summary.avg_llm_ttft_total_ms ?? providerTtfb)} provider_ttft=${formatMs(providerTtfb)} provider_p95=${formatMs(summary.p95_llm_provider_ttfb_ms)} tts_first_audio=${formatMs(ttsTtfb)}`,
    `phrase first_3_words=${formatMs(summary.avg_first_token_to_3_words_ms)} first_6_words=${formatMs(summary.avg_first_token_to_6_words_ms)} speakable=${formatMs(summary.avg_first_token_to_speakable_phrase_ms)} max_token_gap=${formatMs(summary.avg_max_inter_token_gap_ms)} speakable_to_audio=${formatMs(summary.avg_speakable_phrase_to_tts_audio_ms)}`,
    `p95 clean=${formatMs(summary.clean_p95_ms ?? summary.clean_p95_transcript_ready_to_playback_ms)} real=${formatMs(summary.real_p95_ms ?? summary.p95_transcript_ready_to_playback_ms)} interrupted=${formatMs(summary.interrupted_p95_transcript_ready_to_playback_ms)} first_turn=${formatMs(summary.first_turn_p95_transcript_ready_to_playback_ms)} later=${formatMs(summary.later_turn_p95_transcript_ready_to_playback_ms)} contributors=${contributors || "n/a"}`,
    `quality modes=${modeDistribution || "n/a"} valid_barge=${summary.valid_barge_in_count || 0} false_barge=${summary.false_barge_in_count || 0} premature=${summary.premature_assistant_start_count || 0} splits=${summary.user_utterance_split_count || 0} cutouts=${summary.voice_cutout_suspected_count || 0} form_failures=${summary.form_pattern_failure_count || 0} guard_rewrites=${summary.style_guard_rewrite_count || 0}`,
    `diagnostics mode=${summary.latency_diagnostic_mode === false ? "off" : "on"} final_commit=${summary.final_transcript_eager_commit === false ? "off" : "on"} vad_only=${summary.vad_only_user_turn_start === false ? "off" : "on"} bot_mute=${summary.mute_user_while_bot_speaking === false ? "off" : "on"} prewarm=${summary.llm_prewarm_enabled === false ? "off" : "on"}`,
    ...(livekitTransportLine ? [livekitTransportLine] : []),
    ...(livekitClientLine ? [livekitClientLine] : []),
    ...(ultravoxLine ? [ultravoxLine] : []),
    ...(humeLine ? [humeLine] : []),
    `tts first_phrase=${summary.tts_first_phrase_flush_enabled ? "on" : "off"} flush=${summary.tts_first_flush_timeout_ms ?? "n/a"}ms words=${summary.tts_first_flush_min_words ?? "n/a"}-${summary.tts_first_flush_max_words ?? "n/a"} after=${summary.tts_after_first_mode || "sentence"} cartesia_buffer=${summary.cartesia_max_buffer_delay_ms ?? "default"} fast_ack=${summary.fast_ack_enabled ? `${summary.fast_ack_timeout_ms}ms` : "off"}`,
    `barge policy assistant_min=${summary.assistant_min_speak_ms_before_barge_in ?? "n/a"}ms user_min=${summary.barge_in_min_speech_ms ?? "n/a"}ms words=${summary.barge_in_min_transcript_words ?? "n/a"} split_window=${summary.utterance_split_window_ms ?? "n/a"}ms resume_window=${summary.user_resume_after_assistant_window_ms ?? "n/a"}ms`,
    `prompt history=${summary.llm_history_messages ?? "n/a"} max_tokens=${summary.llm_max_tokens ?? "n/a"} temp=${summary.llm_temperature ?? "n/a"} echo_suppression=${summary.echo_suppression_ms ?? "n/a"}ms echo_drops=${summary.echo_suppressed_count || 0}`,
    `guards cancellations=${summary.active_llm_cancelled_count || 0} stale_llm=${summary.stale_llm_completed_count || 0} phantom_prevented=${summary.phantom_turn_prevented_count || 0} ultravox_clears=${summary.ultravox_playback_clear_buffer_count || 0}`,
    "-".repeat(88),
  ];

  const turnLines = (summary.turns || [])
    .filter((turn) => ["success", "interrupted", "failed"].includes(turn.outcome))
    .slice(-6)
    .map(turnSummaryLine);
  if (turnLines.length) {
    lines.push(...turnLines, "-".repeat(88));
  }

  const slowLines = (summary.turns || [])
    .filter((turn) => Number(turn.latency?.ultravox_response_latency_ms ?? turn.latency?.ultravox_processing_latency_ms ?? turn.latency?.transcript_ready_to_playback_ms ?? turn.latency?.perceived_response_latency_ms) > 2000)
    .slice(-4)
    .map(slowTurnLine)
    .filter(Boolean);
  if (slowLines.length) {
    lines.push(...slowLines, "-".repeat(88));
  }

  const eventLines = (summary.latest_events || []).slice(-36).map(terminalEventLine);
  if (eventLines.length) {
    lines.push(...eventLines);
  } else {
    lines.push("[waiting] no backend bot events for this call yet");
  }

  botTerminalEl.textContent = lines.join("\n");
  botTerminalEl.scrollTop = botTerminalEl.scrollHeight;
}

function renderMetrics(summary) {
  const providerMetrics = summary.provider_metrics || {};
  const llmProvider = summary.llm_provider || state.llmProvider;
  const llmModel = summary.llm_model || state.llmModel;
  const llmProviderMetrics =
    providerMetrics[llmProvider] ||
    providerMetrics.gemini ||
    providerMetrics.openai ||
    providerMetrics.groq ||
    providerMetrics.unknown;
  const providerTtfb =
    summary.avg_llm_provider_ttfb_ms ??
    summary.avg_llm_ttfb_ms ??
    llmProviderMetrics?.TTFBMetricsData;
  const ttsProvider = summary.tts_provider || (llmProvider === "ultravox" ? "ultravox" : "cartesia");
  const ttsTtfb =
    summary.avg_tts_ttfb_ms ??
    providerMetrics[ttsProvider]?.TTFBMetricsData ??
    providerMetrics.cartesia?.TTFBMetricsData ??
    providerMetrics.ultravox?.TTFBMetricsData;
  metricsStatusEl.textContent = summary.latest_call_id || state.callId ? "Tracking" : "Waiting";
  const activeAgents = Number(summary.active_agents || 0);
  state.agentRunning = activeAgents > 0 && summary.latest_call_id === state.callId;
  killAgentButton.disabled = activeAgents === 0;
  if (state.transportProvider === "hume_evi") {
    startAgentButton.disabled = true;
    killAgentButton.disabled = true;
  } else if (activeAgents === 0 && state.roomUrl) {
    startAgentButton.disabled = false;
  }
  renderLatencyPanel(summary, providerTtfb, ttsTtfb);
  renderBotTerminal(summary, providerTtfb, ttsTtfb);
  renderDiagnosticMode(summary);
}

function resetMetricsUi() {
  renderMetrics({
    latest_call_id: state.callId,
    total_turns: 0,
    active_agents: 0,
    llm_started_on_counts: {},
    error_count_by_provider: {},
    turns: [],
    latest_events: [],
    transport_provider: state.transportProvider,
    room_name: state.roomName,
    stt_provider: state.sttProvider,
    stt_model: state.deepgramModel,
    llm_provider: state.llmProvider,
    llm_model: state.llmModel,
    tts_provider:
      state.transportProvider === "hume_evi"
        ? "hume_evi"
        : state.llmProvider === "ultravox"
          ? "ultravox"
          : "cartesia",
    tts_model:
      state.transportProvider === "hume_evi"
        ? "hume-evi"
        : state.llmProvider === "ultravox"
          ? state.llmModel
          : "sonic-3",
    livekit_audio_in_sample_rate: state.livekitAudioInSampleRate,
    livekit_audio_out_sample_rate: state.livekitAudioOutSampleRate,
    livekit_audio_out_bitrate: state.livekitAudioOutBitrate,
    livekit_audio_out_10ms_chunks: state.livekitAudioOut10msChunks,
    livekit_audio_out_auto_silence: state.livekitAudioOutAutoSilence,
    livekit_browser_echo_cancellation: state.livekitBrowserEchoCancellation,
    livekit_browser_noise_suppression: state.livekitBrowserNoiseSuppression,
    livekit_browser_auto_gain_control: state.livekitBrowserAutoGainControl,
    livekit_browser_audio_sample_rate: state.livekitBrowserAudioSampleRate,
    ultravox_turn_endpoint_delay_seconds: null,
    ultravox_minimum_turn_duration_seconds: null,
    ultravox_minimum_interruption_duration_seconds: null,
    ultravox_frame_activation_threshold: null,
    ultravox_client_buffer_size_ms: null,
    ultravox_media_idle_timeout_seconds: null,
    avg_hume_first_audio_output_ms: null,
    p95_hume_first_audio_output_ms: null,
    avg_hume_first_audio_playing_ms: null,
    p95_hume_first_audio_playing_ms: null,
    avg_hume_audio_output_to_playback_ms: null,
    tts_text_aggregation_mode: "sentence",
    user_turn_stop_timeout: 5,
    llm_history_messages: 2,
    llm_max_tokens: 32,
    llm_temperature: 0,
    latency_diagnostic_mode: true,
    final_transcript_eager_commit: true,
    vad_only_user_turn_start: true,
    mute_user_while_bot_speaking: false,
    llm_prewarm_enabled: true,
    echo_suppression_ms: 0,
    tts_first_phrase_flush_enabled: true,
    tts_first_flush_timeout_ms: 150,
    tts_first_flush_min_words: 2,
    tts_first_flush_max_words: 6,
    tts_after_first_mode: "sentence",
    cartesia_max_buffer_delay_ms: 100,
    fast_ack_enabled: false,
    fast_ack_timeout_ms: 350,
    assistant_min_speak_ms_before_barge_in: 400,
    barge_in_min_speech_ms: 300,
    barge_in_min_transcript_words: 2,
    utterance_split_window_ms: 1200,
    user_resume_after_assistant_window_ms: 800,
    valid_barge_in_count: 0,
    false_barge_in_count: 0,
    premature_assistant_start_count: 0,
    user_utterance_split_count: 0,
    voice_cutout_suspected_count: 0,
    form_pattern_failure_count: 0,
    style_guard_rewrite_count: 0,
    conversation_mode_counts: {},
  });
  renderTranscript({ call_id: state.callId, items: [], stt_events: [] });
}

function renderTranscript(transcript) {
  transcriptStatusEl.textContent = transcript.call_id ? "Tracking" : "Waiting";
  transcriptFeedEl.innerHTML = "";
  const items = (transcript.items || []).slice(-24);
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "transcript-row";
    empty.innerHTML =
      '<div class="transcript-role">ASR</div><div><p class="transcript-text">No transcript yet</p></div>';
    transcriptFeedEl.appendChild(empty);
  } else {
    items.forEach((item) => {
      const row = document.createElement("div");
      const roleClass = item.role === "assistant" ? "assistant" : "user";
      const source = item.metadata?.frame_type || "final";
      row.className = "transcript-row";
      row.innerHTML = `
        <div class="transcript-role ${roleClass}">${item.role || "user"}</div>
        <div>
          <p class="transcript-text"></p>
          <div class="transcript-meta">${item.turn_id || ""} · ${shortTime(item.timestamp_wall_iso)} · ${source}</div>
        </div>
      `;
      row.querySelector(".transcript-text").textContent = item.text || "";
      transcriptFeedEl.appendChild(row);
    });
  }

  const sttRows = (transcript.stt_events || [])
    .slice(-10)
    .reverse()
    .map((event) => {
      const preview = event.metadata?.text_preview || event.metadata?.transcript || "";
      return `${shortTime(event.timestamp_wall_iso)} · ${event.event_name}${preview ? ` · ${preview}` : ""}`;
    });
  renderTranscriptList(sttEventsEl, sttRows, "No STT events yet");
}

function renderTranscriptList(listEl, rows, emptyText) {
  listEl.innerHTML = "";
  if (!rows.length) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    listEl.appendChild(item);
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("li");
    item.textContent = row;
    listEl.appendChild(item);
  });
}

async function refreshMetrics() {
  const callParam = state.callId && state.callHasStarted ? `?call_id=${encodeURIComponent(state.callId)}` : "";
  let summaryResponse = await fetch(`/api/analytics/summary${callParam}`);
  if (!summaryResponse.ok) {
    throw new Error(`Metrics request failed: HTTP ${summaryResponse.status}`);
  }
  let summary = await summaryResponse.json();
  if (state.callId && summary.event_count === 0 && Number(summary.active_agents || 0) > 0) {
    summaryResponse = await fetch("/api/analytics/summary");
    if (!summaryResponse.ok) {
      throw new Error(`Metrics request failed: HTTP ${summaryResponse.status}`);
    }
    summary = await summaryResponse.json();
  }
  if (summary.latest_call_id && Number(summary.active_agents || 0) > 0 && summary.latest_call_id !== state.callId) {
    state.callId = summary.latest_call_id;
    state.callHasStarted = true;
  }
  const transcriptCallId = summary.latest_call_id || (state.callHasStarted ? state.callId : null);
  const transcriptParam = transcriptCallId ? `?call_id=${encodeURIComponent(transcriptCallId)}` : "";
  const transcriptResponse = await fetch(`/api/analytics/transcript${transcriptParam}`);
  if (!transcriptResponse.ok) {
    throw new Error(`Transcript request failed: HTTP ${transcriptResponse.status}`);
  }
  renderMetrics(summary);
  renderTranscript(await transcriptResponse.json());
}

function startMetricsPolling() {
  if (state.metricsTimer) {
    window.clearInterval(state.metricsTimer);
  }
  refreshMetrics().catch((error) => log(error.message));
  state.metricsTimer = window.setInterval(() => {
    refreshMetrics().catch((error) => log(error.message));
  }, 2000);
}

async function postJson(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return payload;
}

function humeMimeType() {
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return types.find((type) => window.MediaRecorder?.isTypeSupported?.(type)) || "";
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",").pop() : result);
    };
    reader.onerror = () => reject(reader.error || new Error("Blob read failed"));
    reader.readAsDataURL(blob);
  });
}

function base64ToBlob(data, mimeType = "audio/wav") {
  const binary = window.atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType });
}

function humeSocketUrl(session) {
  const url = new URL(session.chat_endpoint || "wss://api.hume.ai/v0/evi/chat");
  url.searchParams.set("access_token", session.access_token);
  if (session.config_id) {
    url.searchParams.set("config_id", session.config_id);
  }
  if (session.config_version !== null && session.config_version !== undefined) {
    url.searchParams.set("config_version", String(session.config_version));
  }
  if (session.session_settings) {
    url.searchParams.set("session_settings", JSON.stringify(session.session_settings));
  }
  url.searchParams.set("verbose_transcription", session.verbose_transcription === false ? "false" : "true");
  return url.toString();
}

function extractHumeText(message) {
  return (
    message?.message?.content ||
    message?.message?.text ||
    message?.content ||
    message?.text ||
    message?.transcript ||
    ""
  );
}

function isDuplicateHumeMessage(role, text, now = performance.now()) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (!role || !normalized) {
    return false;
  }
  const previous = state.humeRecentMessages[role];
  if (previous && previous.text === normalized && now - previous.at <= 1800) {
    return true;
  }
  state.humeRecentMessages[role] = { text: normalized, at: now };
  return false;
}

function humeClientEventName(type) {
  return `hume.client.${String(type || "message").replace(/[^a-zA-Z0-9]+/g, "_").toLowerCase()}`;
}

function renderHumePlaceholder(message = "Ready for Hume EVI") {
  callFrameEl.innerHTML = `
    <div class="livekit-room-panel">
      <div>
        <p class="eyebrow">Hume EVI</p>
        <h2>Direct Speech-to-Speech</h2>
      </div>
      <div class="livekit-room-meta">
        <span>${escapeHtml(state.callId || "session pending")}</span>
        <span id="humePlaybackStatus">${escapeHtml(message)}</span>
      </div>
      <div id="humeAudioMount" class="livekit-audio-mount"></div>
    </div>
  `;
}

function setHumePlaybackStatus(message) {
  const status = document.querySelector("#humePlaybackStatus");
  if (status) {
    status.textContent = message;
  }
}

async function prepareHumeEviSession() {
  stopLiveKitStats("hume_evi");
  disconnectHumeEvi("new_session");
  setStatus("Preparing Hume EVI");
  const session = await postJson("/api/hume/evi/session", {});
  setTransport("hume_evi");
  state.humeSession = session;
  state.humeRecentMessages = {};
  state.humeFirstAudioAt = null;
  state.humeFirstAudioPlayingAt = null;
  state.humeLastUserMessageAt = null;
  state.humeLastAssistantAudioAt = null;
  state.roomUrl = session.chat_endpoint;
  state.roomToken = session.access_token;
  state.roomName = "hume-evi-direct";
  state.callId = session.call_id;
  state.sessionId = session.session_id;
  state.callHasStarted = true;
  state.agentRunning = false;
  roomUrlEl.value = session.chat_endpoint;
  resetMetricsUi();
  renderHumePlaceholder("Click Join Call to connect microphone");
  startAgentButton.disabled = true;
  joinButton.disabled = false;
  openRoomButton.disabled = true;
  killAgentButton.disabled = true;
  leaveButton.disabled = true;
  setStatus("Hume ready");
  log("Hume EVI ready", {
    call_id: state.callId,
    config_id: session.config_id || "default",
    verbose_transcription: session.verbose_transcription,
    stopped_agents: session.stopped_agents || [],
  });
  startMetricsPolling();
}

async function startHumeRecorder(socket) {
  const mimeType = humeMimeType();
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
    video: false,
  });
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  recorder.ondataavailable = async (event) => {
    if (!event.data?.size || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    try {
      socket.send(
        JSON.stringify({
          type: "audio_input",
          data: await blobToBase64(event.data),
        })
      );
    } catch (error) {
      sendClientEvent("hume.client.audio_input_error", {
        error_message: error.message,
      });
    }
  };
  recorder.onerror = (event) => {
    sendClientEvent("hume.client.recorder_error", {
      error_message: event.error?.message || "MediaRecorder error",
    });
  };
  recorder.start(100);
  state.humeMicStream = stream;
  state.humeRecorder = recorder;
  sendClientEvent("hume.client.audio_capture_started", {
    audio_mime_type: mimeType || "browser-default",
  });
}

function stopHumeAudio(reason = "stopped") {
  state.humeAudioQueue = [];
  if (state.humeCurrentAudio) {
    try {
      state.humeCurrentAudio.pause();
      state.humeCurrentAudio.currentTime = 0;
    } catch {
      // Best effort cleanup for browser-created audio elements.
    }
    state.humeCurrentAudio = null;
  }
  state.humeAudioPlaying = false;
  sendClientEvent("hume.client.audio_stopped", { reason });
}

function playNextHumeAudio() {
  if (state.humeAudioPlaying || !state.humeAudioQueue.length) {
    return;
  }
  const item = state.humeAudioQueue.shift();
  const url = URL.createObjectURL(item.blob);
  const audio = new Audio(url);
  audio.autoplay = true;
  audio.playsInline = true;
  audio.volume = 1;
  state.humeAudioPlaying = true;
  state.humeCurrentAudio = audio;
  audio.onplaying = () => {
    const now = performance.now();
    state.humeLastAssistantAudioAt = now;
    if (!state.humeFirstAudioPlayingAt) {
      state.humeFirstAudioPlayingAt = now;
      sendClientEvent("hume.client.first_audio_playing", {
        playback_delay_ms: Math.round(now - item.receivedAt),
        hume_latency_ms: state.humeLastUserMessageAt
          ? Math.round(now - state.humeLastUserMessageAt)
          : null,
        audio_queue_depth: state.humeAudioQueue.length,
      });
    }
    sendClientEvent("hume.client.audio_playing", {
      playback_delay_ms: Math.round(now - item.receivedAt),
      hume_latency_ms: state.humeLastUserMessageAt
        ? Math.round(now - state.humeLastUserMessageAt)
        : null,
      audio_queue_depth: state.humeAudioQueue.length,
    });
  };
  audio.onended = () => {
    URL.revokeObjectURL(url);
    state.humeAudioPlaying = false;
    state.humeCurrentAudio = null;
    playNextHumeAudio();
  };
  audio.onerror = () => {
    URL.revokeObjectURL(url);
    state.humeAudioPlaying = false;
    state.humeCurrentAudio = null;
    sendClientEvent("hume.client.audio_playback_error", {
      error_message: audio.error?.message || "Hume audio playback error",
    });
    playNextHumeAudio();
  };
  audio.play().catch((error) => {
    URL.revokeObjectURL(url);
    state.humeAudioPlaying = false;
    state.humeCurrentAudio = null;
    setHumePlaybackStatus("Browser blocked audio playback");
    sendClientEvent("hume.client.audio_autoplay_blocked", {
      error_message: error.message,
    });
  });
}

function handleHumeMessage(message) {
  const type = message?.type || "unknown";
  const text = extractHumeText(message);
  const role =
    type === "user_message" ? "user" : type === "assistant_message" ? "assistant" : null;
  const now = performance.now();
  if (role && isDuplicateHumeMessage(role, text, now)) {
    sendClientEvent("hume.client.duplicate_message_suppressed", {
      message_type: type,
      text_preview: text ? truncate(text, 120) : undefined,
    });
    return;
  }
  if (type === "audio_output" && message.data) {
    const receivedAt = performance.now();
    if (!state.humeFirstAudioAt) {
      state.humeFirstAudioAt = receivedAt;
      sendClientEvent("hume.client.first_audio_output", {
        hume_latency_ms: state.humeLastUserMessageAt
          ? Math.round(receivedAt - state.humeLastUserMessageAt)
          : null,
      });
    }
    state.humeAudioQueue.push({
      blob: base64ToBlob(message.data, "audio/wav"),
      receivedAt,
    });
    setHumePlaybackStatus("Playing");
    sendClientEvent("hume.client.audio_output", {
      audio_queue_depth: state.humeAudioQueue.length,
      audio_output_count: 1,
    });
    playNextHumeAudio();
    return;
  }
  if (type === "user_interruption") {
    stopHumeAudio("user_interruption");
  }
  if (type === "user_message") {
    state.humeLastUserMessageAt = now;
    state.humeFirstAudioAt = null;
    state.humeFirstAudioPlayingAt = null;
    stopHumeAudio("user_message");
  }
  if (type === "chat_metadata") {
    state.humeChatId = message.chat_id || message.chatId || null;
    state.humeChatGroupId = message.chat_group_id || message.chatGroupId || null;
  }
  sendClientEvent(humeClientEventName(type), {
    message_type: type,
    transcript: text || undefined,
    text_preview: text ? truncate(text, 120) : undefined,
    chat_id: message.chat_id || message.chatId || state.humeChatId || undefined,
    chat_group_id: message.chat_group_id || message.chatGroupId || state.humeChatGroupId || undefined,
  });
}

async function joinHumeEviSession() {
  if (!state.humeSession?.access_token) {
    throw new Error("Create a Hume EVI session first.");
  }
  if (state.humeSocket && state.humeSocket.readyState === WebSocket.OPEN) {
    log("Hume EVI already connected", { call_id: state.callId });
    return;
  }
  renderHumePlaceholder("Connecting");
  const socket = new WebSocket(humeSocketUrl(state.humeSession));
  state.humeSocket = socket;
  setStatus("Joining Hume");

  socket.onopen = async () => {
    setStatus("In Hume EVI");
    setHumePlaybackStatus("Microphone active");
    leaveButton.disabled = false;
    joinButton.disabled = true;
    startAgentButton.disabled = true;
    state.callHasStarted = true;
    sendClientEvent("hume.client.connected", {
      config_id: state.humeSession.config_id || "default",
      config_version: state.humeSession.config_version,
      verbose_transcription: state.humeSession.verbose_transcription,
    });
    try {
      if (state.humeSession.session_settings) {
        socket.send(JSON.stringify(state.humeSession.session_settings));
        sendClientEvent("hume.client.session_settings_sent", {
          config_id: state.humeSession.config_id || "default",
        });
      }
      await startHumeRecorder(socket);
    } catch (error) {
      setStatus("Hume mic error");
      setHumePlaybackStatus("Microphone failed");
      sendClientEvent("hume.client.microphone_error", {
        error_message: error.message,
      });
      log("Hume microphone error", { error_message: error.message });
    }
  };
  socket.onmessage = (event) => {
    try {
      handleHumeMessage(JSON.parse(event.data));
    } catch (error) {
      sendClientEvent("hume.client.message_parse_error", {
        error_message: error.message,
      });
    }
  };
  socket.onerror = () => {
    setStatus("Hume error");
    setHumePlaybackStatus("Socket error");
    sendClientEvent("hume.client.socket_error", {});
  };
  socket.onclose = (event) => {
    disconnectHumeEvi("socket_closed", { close_code: event.code, close_reason: event.reason });
  };
}

function disconnectHumeEvi(reason = "leave", metadata = {}) {
  if (state.humeRecorder && state.humeRecorder.state !== "inactive") {
    state.humeRecorder.stop();
  }
  state.humeRecorder = null;
  if (state.humeMicStream) {
    state.humeMicStream.getTracks().forEach((track) => track.stop());
  }
  state.humeMicStream = null;
  stopHumeAudio(reason);
  state.humeFirstAudioAt = null;
  state.humeFirstAudioPlayingAt = null;
  state.humeLastUserMessageAt = null;
  state.humeLastAssistantAudioAt = null;
  state.humeRecentMessages = {};
  if (state.humeSocket && state.humeSocket.readyState <= WebSocket.OPEN) {
    state.humeSocket.close();
  }
  state.humeSocket = null;
  if (state.transportProvider === "hume_evi") {
    setStatus("Left Hume");
    setHumePlaybackStatus("Disconnected");
    leaveButton.disabled = true;
    joinButton.disabled = !state.humeSession;
    startAgentButton.disabled = true;
    sendClientEvent("hume.client.disconnected", {
      reason,
      ...metadata,
    });
  }
}

async function joinDailyRoom() {
  if (!state.callFrame) {
    callFrameEl.innerHTML = "";
    state.callFrame = window.DailyIframe.createFrame(callFrameEl, {
      showLeaveButton: true,
      iframeStyle: {
        width: "100%",
        height: "100%",
        minHeight: "62vh",
        border: "0",
      },
    });
    state.callFrame.on("joined-meeting", () => {
      setStatus("In call");
      leaveButton.disabled = false;
      joinButton.disabled = true;
      log("Joined meeting");
    });
    state.callFrame.on("joining-meeting", (event) => {
      log("Daily joining", describeDailyEvent(event));
    });
    state.callFrame.on("loaded", (event) => {
      log("Daily iframe loaded", describeDailyEvent(event));
    });
    state.callFrame.on("left-meeting", () => {
      setStatus("Left call");
      leaveButton.disabled = true;
      joinButton.disabled = false;
      log("Left meeting");
    });
    state.callFrame.on("participant-joined", (event) => {
      log("Participant joined", describeDailyEvent(event));
    });
    state.callFrame.on("participant-left", (event) => {
      log("Participant left", describeDailyEvent(event));
    });
    state.callFrame.on("error", (event) => {
      setStatus("Daily error");
      log("Daily error", describeDailyEvent(event));
    });
  }
  setStatus("Joining");
  const joinOptions = { url: state.roomUrl };
  if (isNonEmptyString(state.roomToken)) {
    joinOptions.token = state.roomToken;
  }
  log("Joining room", { transport_provider: "daily", url: joinOptions.url, has_token: Object.hasOwn(joinOptions, "token") });
  await Promise.race([
    state.callFrame.join(joinOptions),
    new Promise((_, reject) => {
      window.setTimeout(
        () =>
          reject(
            new Error(
              "Embedded Daily join timed out after 20 seconds. Use Open Daily Room to join directly."
            )
          ),
        20000
      );
    }),
  ]);
}

function getLiveKitClient() {
  return window.LivekitClient || window.LiveKitClient || window.livekitClient;
}

function iterableValues(collection) {
  if (!collection) {
    return [];
  }
  if (typeof collection.values === "function") {
    return Array.from(collection.values());
  }
  return Object.values(collection);
}

function describeLiveKitParticipant(participant) {
  if (!participant) {
    return null;
  }
  return {
    identity: participant.identity,
    sid: participant.sid,
    local: Boolean(participant.isLocal || participant.local),
    connection_quality: String(participant.connectionQuality ?? ""),
  };
}

function describeTrackPublication(publication) {
  if (!publication) {
    return null;
  }
  return {
    sid: publication.trackSid || publication.sid,
    kind: publication.kind,
    source: publication.source,
    muted: Boolean(publication.isMuted || publication.muted),
    subscribed: Boolean(publication.isSubscribed || publication.subscribed),
  };
}

function roundMetric(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return null;
  }
  const multiplier = 10 ** digits;
  return Math.round(Number(value) * multiplier) / multiplier;
}

function audioElementStats(element) {
  return {
    participant: element.dataset.participant || null,
    paused: element.paused,
    ended: element.ended,
    muted: element.muted,
    volume: element.volume,
    ready_state: element.readyState,
    network_state: element.networkState,
    current_time: roundMetric(element.currentTime),
  };
}

function attachAudioElementDiagnostics(element, publication, participant) {
  const events = [
    "playing",
    "waiting",
    "stalled",
    "suspend",
    "pause",
    "ended",
    "error",
    "canplay",
    "emptied",
  ];
  events.forEach((eventName) => {
    element.addEventListener(eventName, () => {
      const error = element.error
        ? {
            code: element.error.code,
            message: element.error.message,
          }
        : null;
      sendClientEvent(`browser.audio.${eventName}`, {
        audio: audioElementStats(element),
        publication: describeTrackPublication(publication),
        participant: describeLiveKitParticipant(participant),
        error,
      });
    });
  });
}

function liveKitConnectionState(room) {
  return String(room?.state || room?.connectionState || room?.engine?.client?.state || "unknown");
}

function liveKitCanPlayAudio(room) {
  if (typeof room?.canPlaybackAudio === "boolean") {
    return room.canPlaybackAudio;
  }
  if (typeof room?.canPlayAudio === "boolean") {
    return room.canPlayAudio;
  }
  return state.livekitAudioEls.some((element) => !element.paused || element.readyState >= 2);
}

function trackStatsReportCandidates(track) {
  return [
    track,
    track?.mediaStreamTrack,
    track?.receiver,
    track?.sender,
    track?._receiver,
    track?._sender,
  ].filter(Boolean);
}

async function getStatsReportFromTrack(track) {
  for (const candidate of trackStatsReportCandidates(track)) {
    if (typeof candidate.getRTCStatsReport === "function") {
      return candidate.getRTCStatsReport();
    }
    if (typeof candidate.getStats === "function") {
      return candidate.getStats();
    }
  }
  return null;
}

function peerConnectionCandidates(room) {
  const candidates = [
    room?.engine?.client?.pcManager?.subscriber?.pc,
    room?.engine?.client?.pcManager?.publisher?.pc,
    room?.engine?.pcManager?.subscriber?.pc,
    room?.engine?.pcManager?.publisher?.pc,
    room?.engine?.subscriber?.pc,
    room?.engine?.publisher?.pc,
    room?.engine?.client?.subscriber?.pc,
    room?.engine?.client?.publisher?.pc,
  ];
  return [...new Set(candidates.filter((candidate) => candidate && typeof candidate.getStats === "function"))];
}

async function collectRtcReports(room) {
  const reports = [];
  const remoteTracks = state.livekitRemoteAudioTracks.map((item) => item.track).filter(Boolean);
  const localTracks = iterableValues(room?.localParticipant?.audioTrackPublications)
    .map((publication) => publication.track)
    .filter(Boolean);
  for (const track of [...remoteTracks, ...localTracks]) {
    const report = await getStatsReportFromTrack(track);
    if (report) {
      reports.push(report);
    }
  }
  for (const pc of peerConnectionCandidates(room)) {
    reports.push(await pc.getStats());
  }
  return reports;
}

function aggregateRtcStats(reports) {
  const totals = {
    inbound_packets_lost: 0,
    inbound_packets_received: 0,
    outbound_packets_sent: 0,
    outbound_bytes_sent: 0,
    jitter_ms: null,
    jitter_buffer_delay_ms: null,
    concealed_audio_samples: 0,
    concealed_audio_pct: null,
    rtt_ms: null,
    candidate_pair_state: null,
  };
  let jitterBufferDelay = 0;
  let jitterBufferEmitted = 0;
  let concealedSamples = 0;
  let totalSamplesReceived = 0;
  for (const report of reports) {
    report.forEach((stat) => {
      const isAudio = stat.kind === "audio" || stat.mediaType === "audio";
      if (stat.type === "inbound-rtp" && isAudio) {
        totals.inbound_packets_lost += Number(stat.packetsLost || 0);
        totals.inbound_packets_received += Number(stat.packetsReceived || 0);
        if (stat.jitter !== undefined) {
          totals.jitter_ms = Math.max(totals.jitter_ms ?? 0, Number(stat.jitter) * 1000);
        }
        jitterBufferDelay += Number(stat.jitterBufferDelay || 0);
        jitterBufferEmitted += Number(stat.jitterBufferEmittedCount || 0);
        concealedSamples += Number(stat.concealedSamples || 0);
        totalSamplesReceived += Number(stat.totalSamplesReceived || 0);
      }
      if (stat.type === "outbound-rtp" && isAudio) {
        totals.outbound_packets_sent += Number(stat.packetsSent || 0);
        totals.outbound_bytes_sent += Number(stat.bytesSent || 0);
      }
      if (stat.type === "remote-inbound-rtp" && isAudio && stat.roundTripTime !== undefined) {
        totals.rtt_ms = Math.max(totals.rtt_ms ?? 0, Number(stat.roundTripTime) * 1000);
      }
      if (
        stat.type === "candidate-pair" &&
        (stat.selected || stat.nominated) &&
        stat.currentRoundTripTime !== undefined
      ) {
        totals.rtt_ms = Math.max(totals.rtt_ms ?? 0, Number(stat.currentRoundTripTime) * 1000);
        totals.candidate_pair_state = stat.state || null;
      }
    });
  }
  const inboundTotal = totals.inbound_packets_received + totals.inbound_packets_lost;
  return {
    ...totals,
    inbound_packet_loss_pct: inboundTotal
      ? roundMetric((totals.inbound_packets_lost / inboundTotal) * 100)
      : null,
    jitter_ms: roundMetric(totals.jitter_ms),
    jitter_buffer_delay_ms: jitterBufferEmitted
      ? roundMetric((jitterBufferDelay / jitterBufferEmitted) * 1000)
      : null,
    concealed_audio_samples: concealedSamples,
    concealed_audio_pct: totalSamplesReceived
      ? roundMetric((concealedSamples / totalSamplesReceived) * 100)
      : null,
    rtt_ms: roundMetric(totals.rtt_ms),
  };
}

async function collectLiveKitClientStats(room) {
  const reports = await collectRtcReports(room);
  const remoteParticipants = iterableValues(room?.remoteParticipants).map(describeLiveKitParticipant);
  return {
    connection_state: liveKitConnectionState(room),
    can_play_audio: liveKitCanPlayAudio(room),
    audio_unlocked: state.livekitAudioUnlocked,
    remote_audio_tracks: state.livekitRemoteAudioTracks.length,
    remote_audio_elements: state.livekitAudioEls.length,
    local_connection_quality: String(room?.localParticipant?.connectionQuality ?? ""),
    remote_participants: remoteParticipants,
    audio_elements: state.livekitAudioEls.map(audioElementStats),
    ...aggregateRtcStats(reports),
  };
}

async function sampleLiveKitStats(room, source = "interval") {
  if (!room || room !== state.livekitRoom) {
    return;
  }
  try {
    const stats = await collectLiveKitClientStats(room);
    state.livekitLastStats = stats;
    sendClientEvent("livekit.client.stats", { source, ...stats });
  } catch (error) {
    sendClientEvent("livekit.client.stats_error", {
      source,
      error_message: error.message,
    });
  }
}

function startLiveKitStats(room) {
  stopLiveKitStats();
  sendClientEvent("livekit.client.stats_started", {
    connection_state: liveKitConnectionState(room),
  });
  sampleLiveKitStats(room, "start");
  state.livekitStatsTimer = window.setInterval(() => {
    sampleLiveKitStats(room, "interval");
  }, 3000);
}

function stopLiveKitStats(reason = "stopped") {
  if (state.livekitStatsTimer) {
    window.clearInterval(state.livekitStatsTimer);
    state.livekitStatsTimer = null;
  }
  if (state.livekitRoom) {
    sendClientEvent("livekit.client.stats_stopped", {
      reason,
      connection_state: liveKitConnectionState(state.livekitRoom),
    });
  }
}

function renderLiveKitPlaceholder(message = "Ready for LiveKit audio") {
  callFrameEl.innerHTML = `
    <div class="livekit-room-panel">
      <div>
        <p class="eyebrow">LiveKit</p>
        <h2>${escapeHtml(transportLabel(state.transportProvider))} Room</h2>
      </div>
      <div class="livekit-room-meta">
        <span>${escapeHtml(state.roomName || "room pending")}</span>
        <span id="livekitPlaybackStatus">${escapeHtml(message)}</span>
        <button id="livekitAudioButton" class="engine-button" type="button">Enable Bot Audio</button>
      </div>
      <div id="livekitAudioMount" class="livekit-audio-mount"></div>
    </div>
  `;
  wireLiveKitAudioButton();
}

function wireLiveKitAudioButton() {
  const button = document.querySelector("#livekitAudioButton");
  if (!button) {
    return;
  }
  button.disabled = !state.livekitRoom;
  button.addEventListener("click", () => {
    startLiveKitAudioPlayback("button").catch((error) => {
      setLiveKitPlaybackStatus("Audio unlock failed");
      log("LiveKit audio unlock failed", { error_message: error.message });
    });
  });
}

function setLiveKitPlaybackStatus(message) {
  const status = document.querySelector("#livekitPlaybackStatus");
  if (status) {
    status.textContent = message;
  }
}

async function startLiveKitAudioPlayback(source = "auto") {
  const room = state.livekitRoom;
  if (!room) {
    return;
  }
  if (typeof room.startAudio === "function") {
    await room.startAudio();
  }
  const results = await Promise.allSettled(
    state.livekitAudioEls.map((element) => {
      element.muted = false;
      element.volume = 1;
      return element.play();
    })
  );
  const rejected = results.filter((result) => result.status === "rejected");
  state.livekitAudioUnlocked = rejected.length === 0 && liveKitCanPlayAudio(room);
  setLiveKitPlaybackStatus(
    state.livekitAudioUnlocked ? "Connected · bot audio enabled" : "Click Enable Bot Audio"
  );
  const button = document.querySelector("#livekitAudioButton");
  if (button) {
    button.disabled = false;
    button.classList.toggle("active", !state.livekitAudioUnlocked);
  }
  log("LiveKit audio playback", {
    source,
    can_play_audio: liveKitCanPlayAudio(room),
    remote_audio_tracks: state.livekitAudioEls.length,
    blocked: rejected.length,
  });
  sendClientEvent("browser.audio.playback", {
    source,
    can_play_audio: liveKitCanPlayAudio(room),
    remote_audio_elements: state.livekitAudioEls.length,
    blocked: rejected.length,
  });
  sampleLiveKitStats(room, `audio_${source}`);
}

async function joinLiveKitRoom() {
  if (!isNonEmptyString(state.roomToken)) {
    throw new Error("Create a LiveKit room first so the browser has a join token.");
  }
  const LiveKit = getLiveKitClient();
  if (!LiveKit?.Room) {
    throw new Error("LiveKit browser client did not load. Check the CDN script/network.");
  }
  if (state.livekitRoom) {
    log("LiveKit already connected", { room_name: state.roomName });
    return;
  }

  renderLiveKitPlaceholder("Requesting microphone");
  const room = new LiveKit.Room({
    adaptiveStream: false,
    dynacast: false,
  });
  state.livekitRoom = room;
  const roomEvent = LiveKit.RoomEvent || {};
  const trackKind = LiveKit.Track?.Kind || {};

  room.on(roomEvent.Connected || "connected", () => {
    setStatus("In call");
    leaveButton.disabled = false;
    joinButton.disabled = true;
    log("LiveKit connected", { room_name: state.roomName });
    sendClientEvent("livekit.client.connected", {
      connection_state: liveKitConnectionState(room),
    });
    startLiveKitStats(room);
    setLiveKitPlaybackStatus("Connected · waiting for bot audio");
    wireLiveKitAudioButton();
  });
  room.on(roomEvent.Disconnected || "disconnected", (reason) => {
    sendClientEvent("livekit.client.disconnected", {
      reason: String(reason || ""),
      connection_state: liveKitConnectionState(room),
    });
    stopLiveKitStats("disconnected");
    setStatus("Left call");
    leaveButton.disabled = true;
    joinButton.disabled = false;
    log("LiveKit disconnected", { reason: String(reason || "") });
    state.livekitRoom = null;
    state.livekitRemoteAudioTracks = [];
    renderLiveKitPlaceholder("Disconnected");
  });
  room.on(roomEvent.Reconnecting || "reconnecting", () => {
    log("LiveKit reconnecting");
    sendClientEvent("livekit.client.reconnecting", {
      connection_state: liveKitConnectionState(room),
    });
  });
  room.on(roomEvent.Reconnected || "reconnected", () => {
    log("LiveKit reconnected");
    sendClientEvent("livekit.client.reconnected", {
      connection_state: liveKitConnectionState(room),
    });
    sampleLiveKitStats(room, "reconnected");
  });
  room.on(roomEvent.ConnectionStateChanged || "connectionStateChanged", (connectionState) => {
    sendClientEvent("livekit.client.connection_state", {
      connection_state: String(connectionState || liveKitConnectionState(room)),
    });
  });
  room.on(roomEvent.ConnectionQualityChanged || "connectionQualityChanged", (quality, participant) => {
    sendClientEvent("livekit.client.connection_quality", {
      quality: String(quality ?? ""),
      participant: describeLiveKitParticipant(participant),
    });
  });
  room.on(roomEvent.AudioPlaybackStatusChanged || "audioPlaybackStatusChanged", () => {
    const canPlay = liveKitCanPlayAudio(room);
    setLiveKitPlaybackStatus(canPlay ? "Connected · bot audio enabled" : "Click Enable Bot Audio");
    log("LiveKit audio status", { can_play_audio: canPlay });
    sendClientEvent("livekit.client.audio_playback_status", { can_play_audio: canPlay });
    wireLiveKitAudioButton();
  });
  room.on(roomEvent.ParticipantConnected || "participantConnected", (participant) => {
    log("LiveKit participant connected", { identity: participant?.identity, sid: participant?.sid });
    sendClientEvent("livekit.client.participant_connected", {
      participant: describeLiveKitParticipant(participant),
    });
  });
  room.on(roomEvent.ParticipantDisconnected || "participantDisconnected", (participant) => {
    log("LiveKit participant disconnected", { identity: participant?.identity, sid: participant?.sid });
    sendClientEvent("livekit.client.participant_disconnected", {
      participant: describeLiveKitParticipant(participant),
    });
  });
  room.on(roomEvent.TrackMuted || "trackMuted", (publication, participant) => {
    sendClientEvent("livekit.client.track_muted", {
      publication: describeTrackPublication(publication),
      participant: describeLiveKitParticipant(participant),
    });
  });
  room.on(roomEvent.TrackUnmuted || "trackUnmuted", (publication, participant) => {
    sendClientEvent("livekit.client.track_unmuted", {
      publication: describeTrackPublication(publication),
      participant: describeLiveKitParticipant(participant),
    });
  });
  room.on(roomEvent.TrackSubscribed || "trackSubscribed", (track, publication, participant) => {
    if (track.kind !== (trackKind.Audio || "audio")) {
      return;
    }
    const element = track.attach();
    element.autoplay = true;
    element.playsInline = true;
    element.controls = false;
    element.muted = false;
    element.volume = 1;
    element.dataset.participant = participant?.identity || participant?.sid || "remote";
    attachAudioElementDiagnostics(element, publication, participant);
    const mount = document.querySelector("#livekitAudioMount") || callFrameEl;
    mount.appendChild(element);
    state.livekitAudioEls.push(element);
    state.livekitRemoteAudioTracks.push({ track, publication, participant });
    log("LiveKit audio subscribed", {
      participant: element.dataset.participant,
      publication: publication?.trackSid || publication?.sid,
    });
    sendClientEvent("livekit.client.track_subscribed", {
      publication: describeTrackPublication(publication),
      participant: describeLiveKitParticipant(participant),
    });
    sampleLiveKitStats(room, "track_subscribed");
    startLiveKitAudioPlayback("track_subscribed").catch((error) => {
      setLiveKitPlaybackStatus("Click Enable Bot Audio");
      log("LiveKit audio autoplay blocked", { error_message: error.message });
      sendClientEvent("browser.audio.autoplay_blocked", { error_message: error.message });
      wireLiveKitAudioButton();
    });
  });
  room.on(roomEvent.TrackUnsubscribed || "trackUnsubscribed", (track, publication, participant) => {
    if (typeof track.detach === "function") {
      track.detach().forEach((element) => element.remove());
    }
    state.livekitRemoteAudioTracks = state.livekitRemoteAudioTracks.filter((item) => item.track !== track);
    sendClientEvent("livekit.client.track_unsubscribed", {
      publication: describeTrackPublication(publication),
      participant: describeLiveKitParticipant(participant),
    });
  });

  setStatus("Joining");
  log("Joining room", {
    transport_provider: "livekit",
    url: state.roomUrl,
    room_name: state.roomName,
    has_token: true,
  });
  await Promise.race([
    room.connect(state.roomUrl, state.roomToken),
    new Promise((_, reject) => {
      window.setTimeout(() => reject(new Error("LiveKit join timed out after 20 seconds.")), 20000);
    }),
  ]);
  try {
    const audioCaptureOptions = {
      echoCancellation: state.livekitBrowserEchoCancellation,
      noiseSuppression: state.livekitBrowserNoiseSuppression,
      autoGainControl: state.livekitBrowserAutoGainControl,
      channelCount: 1,
    };
    if (state.livekitBrowserAudioSampleRate) {
      audioCaptureOptions.sampleRate = Number(state.livekitBrowserAudioSampleRate);
    }
    await room.localParticipant.setMicrophoneEnabled(true, audioCaptureOptions);
    sendClientEvent("livekit.client.microphone_enabled", {
      audio_capture_options: audioCaptureOptions,
    });
    await startLiveKitAudioPlayback("join_click");
  } catch (error) {
    setLiveKitPlaybackStatus("Click Enable Bot Audio");
    log("LiveKit audio needs click", { error_message: error.message });
    sendClientEvent("browser.audio.unlock_needed", { error_message: error.message });
    wireLiveKitAudioButton();
  }
}

async function leaveLiveKitRoom() {
  if (!state.livekitRoom) {
    return;
  }
  stopLiveKitStats("leave");
  state.livekitAudioEls.forEach((element) => element.remove());
  state.livekitAudioEls = [];
  state.livekitRemoteAudioTracks = [];
  state.livekitRoom.disconnect();
  state.livekitRoom = null;
  setStatus("Left call");
  leaveButton.disabled = true;
  joinButton.disabled = false;
  renderLiveKitPlaceholder("Disconnected");
}

prepareButton.addEventListener("click", async () => {
  try {
    if (state.transportProvider === "hume_evi") {
      await prepareHumeEviSession();
      return;
    }
    stopLiveKitStats("new_room");
    setStatus("Creating room");
    const payload = {
      transport_provider: state.transportProvider,
    };
    if (state.transportProvider === "daily") {
      payload.daily_geo = state.dailyGeo || null;
      payload.force_create_room = Boolean(state.dailyGeo);
    }
    const room = await postJson("/api/rooms", payload);
    setTransport(room.transport_provider || state.transportProvider);
    state.roomUrl = room.room_url;
    state.roomToken = room.room_token;
    state.roomName = room.room_name || null;
    state.callId = room.call_id;
    state.sessionId = room.session_id;
    state.callHasStarted = false;
    state.agentRunning = false;
    roomUrlEl.value = state.roomUrl;
    resetMetricsUi();
    startAgentButton.disabled = false;
    joinButton.disabled = false;
    openRoomButton.disabled = state.transportProvider === "livekit";
    setStatus("Room ready");
    log("Room ready", {
      source: room.source,
      call_id: state.callId,
      transport_provider: state.transportProvider,
      room_name: state.roomName,
      daily_geo: state.transportProvider === "daily" ? state.dailyGeo || null : null,
      room_geo: room.room_geo || null,
    });
    if ((room.stopped_agents || []).length) {
      log("Stopped previous agent", { stopped_agents: room.stopped_agents });
    }
  } catch (error) {
    setStatus("Room error");
    log(error.message);
  }
});

startAgentButton.addEventListener("click", async () => {
  try {
    if (state.transportProvider === "hume_evi") {
      log("Hume EVI runs directly in the browser. Use Join Call.");
      return;
    }
    state.roomUrl = roomUrlEl.value || state.roomUrl;
    if (!state.roomUrl) {
      throw new Error(`Create or enter a ${transportLabel(state.transportProvider)} room first.`);
    }
    if (state.agentRunning) {
      log("Agent already running", { call_id: state.callId });
      return;
    }
    setStatus("Starting agent");
    startAgentButton.disabled = true;
    const payload = {
      transport_provider: state.transportProvider,
      room_url: state.roomUrl,
      room_token: state.transportProvider === "daily" ? state.roomToken : null,
      room_name: state.roomName,
      stt_provider: state.sttProvider,
      deepgram_model: state.deepgramModel,
      llm_provider: state.llmProvider,
      llm_model: state.llmModel,
      daily_geo: state.transportProvider === "daily" ? state.dailyGeo || null : null,
    };
    if (!state.callHasStarted) {
      payload.call_id = state.callId;
      payload.session_id = state.sessionId;
    }
    const previousCallId = state.callId;
    const result = await postJson("/api/agent/start", payload);
    state.callId = result.call_id;
    state.sessionId = result.session_id;
    state.roomName = result.room_name || state.roomName;
    state.callHasStarted = true;
    state.agentRunning = true;
    if (state.callId !== previousCallId) {
      resetMetricsUi();
    }
    setStatus(result.already_running ? "Agent already running" : "Agent running");
    killAgentButton.disabled = false;
    log("Agent status", {
      started: result.started,
      already_running: result.already_running,
      call_id: result.call_id,
      transport_provider: result.transport_provider,
      room_name: result.room_name,
      stt_provider: result.stt_provider,
      deepgram_model: result.deepgram_model,
      llm_provider: result.llm_provider,
      llm_model: result.llm_model,
      daily_geo: state.transportProvider === "daily" ? state.dailyGeo || null : null,
      stopped_agents: result.stopped_agents || [],
    });
    startMetricsPolling();
  } catch (error) {
    setStatus("Agent error");
    if (state.roomUrl) {
      startAgentButton.disabled = false;
    }
    state.agentRunning = false;
    log(error.message);
  }
});

killAgentButton.addEventListener("click", async () => {
  try {
    setStatus("Killing agent");
    const result = await postJson("/api/agent/stop", {
      call_id: state.callId,
    });
    killAgentButton.disabled = true;
    startAgentButton.disabled = !state.roomUrl;
    state.agentRunning = false;
    setStatus(result.stopped ? "Agent killed" : "No agent running");
    log("Agent stopped", result);
    refreshMetrics().catch((error) => log(error.message));
  } catch (error) {
    setStatus("Kill error");
    log(error.message);
  }
});

dailyTransportButton.addEventListener("click", () => {
  stopLiveKitStats("transport_switch");
  disconnectHumeEvi("transport_switch");
  setTransport("daily");
  state.roomUrl = "";
  state.roomToken = null;
  state.roomName = null;
  state.livekitRemoteAudioTracks = [];
  roomUrlEl.value = "";
  startAgentButton.disabled = true;
  joinButton.disabled = true;
  openRoomButton.disabled = true;
  log("Transport selected", { transport_provider: state.transportProvider });
});

livekitTransportButton.addEventListener("click", () => {
  stopLiveKitStats("transport_switch");
  disconnectHumeEvi("transport_switch");
  setTransport("livekit");
  state.roomUrl = "";
  state.roomToken = null;
  state.roomName = null;
  state.livekitRemoteAudioTracks = [];
  roomUrlEl.value = "";
  startAgentButton.disabled = true;
  joinButton.disabled = true;
  openRoomButton.disabled = true;
  renderLiveKitPlaceholder("Create a room to connect");
  log("Transport selected", { transport_provider: state.transportProvider });
});

humeTransportButton.addEventListener("click", () => {
  stopLiveKitStats("transport_switch");
  disconnectHumeEvi("transport_switch");
  if (state.livekitRoom) {
    leaveLiveKitRoom().catch((error) => log(error.message));
  }
  setTransport("hume_evi");
  state.roomUrl = "";
  state.roomToken = null;
  state.roomName = null;
  state.callId = null;
  state.sessionId = null;
  state.callHasStarted = false;
  state.agentRunning = false;
  state.humeSession = null;
  roomUrlEl.value = "";
  startAgentButton.disabled = true;
  joinButton.disabled = true;
  openRoomButton.disabled = true;
  killAgentButton.disabled = true;
  renderHumePlaceholder("Create a Hume EVI session");
  resetMetricsUi();
  log("Transport selected", { transport_provider: state.transportProvider });
});

dailyRegionAutoButton.addEventListener("click", () => {
  setDailyRegion(null);
  log("Daily region selected", { daily_geo: null, behavior: "provider_auto_or_env_room" });
});

dailyRegionFrankfurtButton.addEventListener("click", () => {
  setDailyRegion("eu-central-1");
  log("Daily region selected", { daily_geo: state.dailyGeo, region: "Frankfurt" });
});

dailyRegionLondonButton.addEventListener("click", () => {
  setDailyRegion("eu-west-2");
  log("Daily region selected", { daily_geo: state.dailyGeo, region: "London" });
});

openRoomButton.addEventListener("click", () => {
  if (state.transportProvider !== "daily") {
    setStatus("Open unavailable");
    log(`${transportLabel(state.transportProvider)} uses the embedded room panel for browser testing.`);
    return;
  }
  state.roomUrl = currentRoomUrl();
  if (!state.roomUrl) {
    setStatus("Open error");
    log("Create or enter a Daily room first.");
    return;
  }
  window.open(state.roomUrl, "_blank", "noopener,noreferrer");
  log("Opened Daily room directly", { url: state.roomUrl });
});

joinButton.addEventListener("click", async () => {
  try {
    state.roomUrl = currentRoomUrl();
    if (state.transportProvider !== "hume_evi" && !state.roomUrl) {
      throw new Error(`Create or enter a ${transportLabel(state.transportProvider)} room first.`);
    }
    if (state.transportProvider === "hume_evi") {
      await joinHumeEviSession();
    } else if (state.transportProvider === "livekit") {
      await joinLiveKitRoom();
    } else {
      await joinDailyRoom();
    }
  } catch (error) {
    setStatus("Join error");
    log(error.message);
  }
});

leaveButton.addEventListener("click", async () => {
  if (state.transportProvider === "hume_evi") {
    disconnectHumeEvi("leave");
    return;
  }
  if (state.transportProvider === "livekit" && state.livekitRoom) {
    await leaveLiveKitRoom();
    return;
  }
  if (state.callFrame) {
    await state.callFrame.leave();
  }
});

fluxButton.addEventListener("click", () => {
  setSttEngine("deepgram_flux", "flux-general-en");
  log("STT engine selected", { stt_provider: state.sttProvider, deepgram_model: state.deepgramModel });
});

novaButton.addEventListener("click", () => {
  setSttEngine("deepgram", "nova-3-general");
  log("STT engine selected", { stt_provider: state.sttProvider, deepgram_model: state.deepgramModel });
});

geminiButton.addEventListener("click", () => {
  const option = optionForProvider("gemini");
  setLlmEngine("gemini", option?.llm_model || "gemini-2.5-flash");
  log("LLM engine selected", { llm_provider: state.llmProvider, llm_model: state.llmModel });
});

groqButton.addEventListener("click", () => {
  const option = optionForProvider("groq");
  setLlmEngine("groq", option?.llm_model || "llama-3.1-8b-instant");
  log("LLM engine selected", { llm_provider: state.llmProvider, llm_model: state.llmModel });
});

openaiButton.addEventListener("click", () => {
  const option = optionForProvider("openai");
  setLlmEngine("openai", option?.llm_model || "gpt-4o-mini");
  log("LLM engine selected", { llm_provider: state.llmProvider, llm_model: state.llmModel });
});

qwenButton.addEventListener("click", () => {
  const option = optionForProvider("qwen");
  setLlmEngine("qwen", option?.llm_model || "qwen3.5-flash");
  log("LLM engine selected", { llm_provider: state.llmProvider, llm_model: state.llmModel });
});

xaiButton.addEventListener("click", () => {
  const option = optionForProvider("xai");
  setLlmEngine("xai", option?.llm_model || "grok-4-1-fast-non-reasoning");
  log("LLM engine selected", { llm_provider: state.llmProvider, llm_model: state.llmModel });
});

ultravoxButton.addEventListener("click", () => {
  const option = optionForProvider("ultravox");
  const wasLiveKit = state.transportProvider === "livekit";
  disconnectHumeEvi("llm_switch");
  setTransport("livekit");
  if (!wasLiveKit) {
    state.roomUrl = "";
    state.roomToken = null;
    state.roomName = null;
    state.callId = null;
    state.sessionId = null;
    state.callHasStarted = false;
    roomUrlEl.value = "";
    startAgentButton.disabled = true;
    joinButton.disabled = true;
    openRoomButton.disabled = true;
    renderLiveKitPlaceholder("Create a room to connect");
  }
  setLlmEngine("ultravox", option?.llm_model || "fixie-ai/ultravox");
  log("UltraVox realtime mode selected", {
    transport_provider: state.transportProvider,
    llm_provider: state.llmProvider,
    llm_model: state.llmModel,
  });
});

mockLlmButton.addEventListener("click", () => {
  const option = optionForProvider("mock");
  setLlmEngine("mock", option?.llm_model || "mock-immediate");
  log("LLM engine selected", { llm_provider: state.llmProvider, llm_model: state.llmModel });
});

diagnosticButton.addEventListener("click", () => {
  const gemini = optionForProvider("gemini");
  setSttEngine("deepgram", "nova-3-general");
  setLlmEngine("gemini", gemini?.llm_model || "gemini-2.5-flash");
  renderDiagnosticMode({
    latency_diagnostic_mode: true,
    llm_history_messages: 2,
    llm_max_tokens: 32,
    user_turn_stop_timeout: 5,
    final_transcript_eager_commit: true,
    vad_only_user_turn_start: true,
    mute_user_while_bot_speaking: false,
    llm_prewarm_enabled: true,
    echo_suppression_ms: 0,
  });
  log("Latency diagnostic mode selected", {
    stt_provider: state.sttProvider,
    deepgram_model: state.deepgramModel,
    llm_provider: state.llmProvider,
    llm_model: state.llmModel,
  });
});

async function loadRuntimeConfig() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) {
      throw new Error(`Config request failed: HTTP ${response.status}`);
    }
    const config = await response.json();
    state.llmOptions = config.llm_options || [];
    state.livekitAudioInSampleRate = config.livekit_audio_in_sample_rate ?? null;
    state.livekitAudioOutSampleRate = config.livekit_audio_out_sample_rate ?? null;
    state.livekitAudioOutBitrate = config.livekit_audio_out_bitrate ?? 96000;
    state.livekitAudioOut10msChunks = config.livekit_audio_out_10ms_chunks ?? 4;
    state.livekitAudioOutAutoSilence = config.livekit_audio_out_auto_silence !== false;
    state.livekitBrowserEchoCancellation = config.livekit_browser_echo_cancellation !== false;
    state.livekitBrowserNoiseSuppression = config.livekit_browser_noise_suppression !== false;
    state.livekitBrowserAutoGainControl = config.livekit_browser_auto_gain_control !== false;
    state.livekitBrowserAudioSampleRate = config.livekit_browser_audio_sample_rate ?? 48000;
    setDailyRegion(config.daily_geo || state.dailyGeo || null);
    setTransport(config.transport_provider || "daily");
    setSttEngine(config.stt_provider, config.deepgram_model);
    const savedLlmProvider = loadSavedLlmProvider();
    const llmProvider = knownLlmProvider(savedLlmProvider)
      ? savedLlmProvider
      : config.llm_provider;
    setLlmEngine(llmProvider, defaultModelForProvider(llmProvider, config.llm_model), {
      persist: false,
    });
    renderDiagnosticMode(config);
    if (state.callId) {
      refreshMetrics().catch((error) => log(error.message));
    } else {
      resetMetricsUi();
    }
  } catch (error) {
    log(error.message);
  }
}

loadRuntimeConfig();
