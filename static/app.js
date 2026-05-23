const state = {
  transport: "livekit",
  sttProvider: "deepgram",
  sttModel: "nova-3-general",
  llmProvider: "groq",
  llmModel: "llama-3.1-8b-instant",
  clientId: "demo",
  callerPhone: "",
  knowledgeBase: "",
  toolsEnabled: true,
  integrationConnected: false,
  roomUrl: null,
  roomName: null,
  roomToken: null,
  callId: null,
  sessionId: null,
  dailyFrame: null,
  livekitRoom: null,
  livekitAudioEls: [],
  livekitRemoteAudioTracks: [],
  livekitStatsTimer: null,
  humeSession: null,
  humeSocket: null,
  humeRecorder: null,
  humeMicStream: null,
  humeAudioQueue: [],
  humeCurrentAudio: null,
  humeAudioPlaying: false,
  humeLastUserAt: null,
  logs: [],
  toolEventKeys: new Set(),
  config: null,
  metricsTimer: null,
  integrationPollTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const transportButtons = $("#transportButtons");
const sttButtons = $("#sttButtons");
const llmButtons = $("#llmButtons");
const prepareButton = $("#prepareButton");
const startAgentButton = $("#startAgentButton");
const joinButton = $("#joinButton");
const leaveButton = $("#leaveButton");
const stopAgentButton = $("#stopAgentButton");
const clientIdInput = $("#clientIdInput");
const callerPhoneInput = $("#callerPhoneInput");
const knowledgeBaseInput = $("#knowledgeBaseInput");
const callNotesOutput = $("#callNotesOutput");
const refreshCallNotesButton = $("#refreshCallNotesButton");
const toolsEnabledInput = $("#toolsEnabledInput");
const connectCalendarButton = $("#connectCalendarButton");
const integrationStatusButton = $("#integrationStatusButton");
const integrationStatusLine = $("#integrationStatusLine");
const roomMount = $("#roomMount");
const roomTitle = $("#roomTitle");
const roomUrl = $("#roomUrl");
const statusEl = $("#status");
const terminalLog = $("#terminalLog");
const transcriptList = $("#transcriptList");
const callIdLabel = $("#callIdLabel");

function setStatus(text) {
  statusEl.textContent = text;
}

function log(message, metadata = {}) {
  const time = new Date().toLocaleTimeString();
  const meta = Object.keys(metadata).length ? ` ${JSON.stringify(metadata)}` : "";
  state.logs.push(`[${time}] ${message}${meta}`);
  state.logs = state.logs.slice(-160);
  terminalLog.textContent = state.logs.join("\n");
  terminalLog.scrollTop = terminalLog.scrollHeight;
}

function ms(value) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "n/a"
    : `${Math.round(Number(value))} ms`;
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

function renderButtonGroup(container, options, activeValue, onClick, valueKey) {
  container.innerHTML = "";
  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option.label;
    button.className = option[valueKey] === activeValue ? "active" : "";
    button.addEventListener("click", () => onClick(option));
    container.appendChild(button);
  });
}

function renderControls() {
  const config = state.config;
  renderButtonGroup(transportButtons, config.transport_options, state.transport, (option) => {
    state.transport = option.transport_provider;
    if (state.transport === "daily" && state.llmProvider === "ultravox") {
      const groq = config.llm_options.find((item) => item.llm_provider === "groq");
      setLlm(groq);
    }
    resetRoom("transport_switch");
    renderControls();
  }, "transport_provider");
  renderButtonGroup(sttButtons, config.stt_options, state.sttProvider, (option) => {
    state.sttProvider = option.stt_provider;
    state.sttModel = option.deepgram_model;
    resetRoom("stt_switch");
    renderControls();
  }, "stt_provider");
  llmButtons.innerHTML = "";
  config.llm_options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option.label;
    button.className = option.llm_provider === state.llmProvider ? "active" : "";
    button.disabled = state.transport === "daily" && option.llm_provider === "ultravox";
    button.addEventListener("click", () => {
      if (button.disabled) return;
      setLlm(option);
      resetRoom("llm_switch");
      renderControls();
    });
    llmButtons.appendChild(button);
  });
  sttButtons.querySelectorAll("button").forEach((button) => {
    button.disabled = state.transport === "hume_evi";
  });
  llmButtons.querySelectorAll("button").forEach((button) => {
    if (state.transport === "hume_evi") button.disabled = true;
  });
  const nangoConfigured = state.config?.integration_catalog?.providers?.some((provider) => provider.id === "nango" && provider.configured);
  const directToolsConfigured = Boolean(state.config?.direct_tools_configured)
    || state.config?.integration_catalog?.providers?.some((provider) => provider.id === "direct" && provider.configured);
  const toolsCompatible = state.transport !== "hume_evi" && state.llmProvider !== "ultravox";
  const toolsReady = toolsCompatible && (directToolsConfigured || (nangoConfigured && state.integrationConnected));
  toolsEnabledInput.disabled = !toolsReady;
  if (!toolsReady) {
    toolsEnabledInput.checked = false;
    state.toolsEnabled = false;
  } else if (state.config?.tools_enabled) {
    toolsEnabledInput.checked = true;
    state.toolsEnabled = true;
  }
  connectCalendarButton.disabled = !nangoConfigured;
  prepareButton.textContent = state.transport === "hume_evi" ? "Create Hume Session" : "Create Room";
  startAgentButton.disabled = state.transport === "hume_evi" || !state.roomUrl;
  joinButton.disabled = !state.roomUrl && !state.humeSession;
}

function setLlm(option) {
  state.llmProvider = option.llm_provider;
  state.llmModel = option.llm_model;
}

function resetRoom(reason) {
  leaveCurrent().catch(() => {});
  state.roomUrl = null;
  state.roomName = null;
  state.roomToken = null;
  state.callId = null;
  state.sessionId = null;
  state.humeSession = null;
  state.toolEventKeys.clear();
  roomUrl.value = "";
  roomTitle.textContent = "Not connected";
  callIdLabel.textContent = "No call";
  renderPlaceholder(`Ready (${reason})`);
}

function renderPlaceholder(text = "Create a room to begin") {
  roomMount.innerHTML = `<div class="placeholder">${escapeHtml(text)}</div>`;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

async function loadConfig() {
  const response = await fetch("/api/config");
  state.config = await response.json();
  state.transport = state.config.transport_provider || "livekit";
  state.sttProvider = state.config.stt_provider || "deepgram";
  state.sttModel = state.config.stt_model || "nova-3-general";
  state.llmProvider = state.config.llm_provider || "groq";
  state.llmModel = state.config.llm_model || "llama-3.1-8b-instant";
  state.clientId = state.config.default_client_id || "demo";
  state.callerPhone = state.config.caller_phone || "";
  state.knowledgeBase = state.config.knowledge_base || "";
  state.toolsEnabled = Boolean(state.config.tools_enabled);
  clientIdInput.value = state.clientId;
  callerPhoneInput.value = state.callerPhone;
  knowledgeBaseInput.value = state.knowledgeBase;
  toolsEnabledInput.checked = state.toolsEnabled;
  renderControls();
  refreshIntegrationStatus().catch(() => {});
  renderPlaceholder();
  setStatus("Ready");
  log("Config loaded", {
    transport: state.transport,
    stt: `${state.sttProvider}/${state.sttModel}`,
    llm: `${state.llmProvider}/${state.llmModel}`,
  });
  startPolling();
}

function requestPayload() {
  return {
    transport_provider: state.transport,
    stt_provider: state.sttProvider,
    deepgram_model: state.sttModel,
    llm_provider: state.llmProvider,
    llm_model: state.llmModel,
    room_url: state.roomUrl,
    room_name: state.roomName,
    call_id: state.callId,
    session_id: state.sessionId,
    client_id: state.clientId,
    caller_phone: state.callerPhone,
    knowledge_base: state.knowledgeBase,
    tools_enabled: state.toolsEnabled && state.transport !== "hume_evi" && state.llmProvider !== "ultravox",
  };
}

async function prepare() {
  syncToolStateFromInputs();
  if (state.transport === "hume_evi") {
    const session = await postJson("/api/hume/evi/session", {
      knowledge_base: state.knowledgeBase,
    });
    state.humeSession = session;
    state.roomUrl = session.chat_endpoint;
    state.roomToken = session.access_token;
    state.roomName = "hume-evi-direct";
    state.callId = session.call_id;
    state.sessionId = session.session_id;
    roomTitle.textContent = "Hume EVI";
    roomUrl.value = session.chat_endpoint;
    callIdLabel.textContent = state.callId;
    renderPlaceholder("Join to connect microphone");
    startPolling();
    renderControls();
    log("Hume session ready", {
      call_id: state.callId,
      config_id: session.config_id || "default",
      kb_chars: session.knowledge_base_chars || 0,
    });
    return;
  }
  const room = await postJson("/api/rooms", {
    transport_provider: state.transport,
  });
  state.roomUrl = room.room_url;
  state.roomToken = room.room_token;
  state.roomName = room.room_name;
  state.callId = room.call_id;
  state.sessionId = room.session_id;
  roomTitle.textContent = state.roomName || state.transport;
  roomUrl.value = state.roomUrl;
  callIdLabel.textContent = state.callId;
  renderPlaceholder(`${state.transport} room ready`);
  startPolling();
  renderControls();
  log("Room ready", {
    transport: state.transport,
    source: room.source,
    call_id: state.callId,
    room_name: state.roomName,
  });
}

async function startAgent() {
  syncToolStateFromInputs();
  const result = await postJson("/api/agent/start", requestPayload());
  log("Agent started", {
    call_id: result.call_id,
    transport: result.transport_provider,
    llm: `${result.llm_provider}/${result.llm_model}`,
    client_id: result.client_id,
    tools_enabled: result.tools_enabled,
    kb_chars: result.knowledge_base_chars || 0,
  });
  setStatus("Agent running");
  startPolling();
}

function syncToolStateFromInputs() {
  state.clientId = (clientIdInput.value || "demo").trim() || "demo";
  state.callerPhone = (callerPhoneInput.value || "").trim();
  state.knowledgeBase = (knowledgeBaseInput.value || "").trim();
  state.toolsEnabled = Boolean(toolsEnabledInput.checked);
}

async function connectCalendar() {
  syncToolStateFromInputs();
  const integrationKey = currentCalendarIntegrationKey();
  const result = await postJson("/api/integrations/nango/connect-session", {
    client_id: state.clientId,
    integration_key: integrationKey,
  });
  integrationStatusLine.textContent = `Calendar connect link expires ${result.expires_at || "soon"}`;
  log("Calendar connect session created", {
    client_id: result.client_id,
    integration_key: result.integration_key,
  });
  window.open(result.connect_link, "_blank", "noopener");
  startIntegrationStatusPolling();
}

async function refreshIntegrationStatus() {
  syncToolStateFromInputs();
  const response = await fetch(`/api/integrations/status?client_id=${encodeURIComponent(state.clientId)}`);
  const status = await response.json();
  if (!response.ok) throw new Error(status.detail || `HTTP ${response.status}`);
  const integrationKey = currentCalendarIntegrationKey();
  const calendar = (status.integrations || []).find((item) => item.integration_key === integrationKey) || status.integrations?.[0];
  const directToolsConfigured = Boolean(state.config?.direct_tools_configured)
    || state.config?.integration_catalog?.providers?.some((provider) => provider.id === "direct" && provider.configured);
  state.integrationConnected = Boolean(calendar?.connection_id && !["not_connected", "pending", "error", "failed", "expired"].includes(String(calendar.status || "").toLowerCase()));
  if ((state.integrationConnected || directToolsConfigured) && state.config?.tools_enabled && state.transport !== "hume_evi" && state.llmProvider !== "ultravox") {
    state.toolsEnabled = true;
    toolsEnabledInput.checked = true;
  }
  integrationStatusLine.textContent = calendar
    ? state.integrationConnected
      ? `${calendar.integration_key}: connected`
      : directToolsConfigured
        ? `${calendar.integration_key}: not connected · direct follow-up tools ready`
        : `${calendar.integration_key}: not connected. Connect Calendar before enabling tools.`
    : directToolsConfigured
      ? "Direct follow-up tools ready"
      : "No integrations configured";
  renderControls();
  if (state.integrationConnected) stopIntegrationStatusPolling();
  return status;
}

function startIntegrationStatusPolling() {
  stopIntegrationStatusPolling();
  let attempts = 0;
  integrationStatusLine.textContent = "Waiting for calendar connection...";
  state.integrationPollTimer = window.setInterval(() => {
    attempts += 1;
    refreshIntegrationStatus().catch((error) => {
      log("Integration status failed", { error: error.message });
    });
    if (attempts >= 40) {
      stopIntegrationStatusPolling();
      if (!state.integrationConnected) {
        integrationStatusLine.textContent = "Calendar still not connected. Finish Nango auth, then click Status.";
      }
    }
  }, 3000);
}

function stopIntegrationStatusPolling() {
  if (state.integrationPollTimer) {
    window.clearInterval(state.integrationPollTimer);
    state.integrationPollTimer = null;
  }
}

function currentCalendarIntegrationKey() {
  return state.config?.integration_catalog?.providers?.[0]?.integrations?.[0]?.integration_key || "google-calendar";
}

async function join() {
  if (state.transport === "daily") return joinDaily();
  if (state.transport === "livekit") return joinLiveKit();
  return joinHume();
}

async function leaveCurrent() {
  if (state.dailyFrame) {
    try {
      await state.dailyFrame.leave();
      state.dailyFrame.destroy();
    } catch {}
    state.dailyFrame = null;
  }
  if (state.livekitRoom) {
    stopLiveKitStats("leave");
    state.livekitAudioEls.forEach((element) => element.remove());
    state.livekitAudioEls = [];
    state.livekitRemoteAudioTracks = [];
    state.livekitRoom.disconnect();
    state.livekitRoom = null;
  }
  disconnectHume("leave");
  leaveButton.disabled = true;
  joinButton.disabled = false;
}

async function joinDaily() {
  if (!state.roomUrl) throw new Error("Create a Daily room first.");
  roomMount.innerHTML = "";
  state.dailyFrame = window.DailyIframe.createFrame(roomMount, {
    showLeaveButton: true,
    iframeStyle: { width: "100%", height: "100%", minHeight: "460px", border: "0" },
  });
  state.dailyFrame.on("joined-meeting", () => {
    setStatus("In Daily");
    leaveButton.disabled = false;
    joinButton.disabled = true;
    sendClientEvent("daily.client.joined", {});
  });
  state.dailyFrame.on("left-meeting", () => {
    setStatus("Left Daily");
    sendClientEvent("daily.client.left", {});
  });
  const joinArgs = { url: state.roomUrl };
  if (typeof state.roomToken === "string" && state.roomToken) {
    joinArgs.token = state.roomToken;
  }
  await state.dailyFrame.join(joinArgs);
}

function getLiveKitClient() {
  return window.LivekitClient || window.LiveKitClient || window.livekitClient;
}

async function joinLiveKit() {
  if (!state.roomToken) throw new Error("Create a LiveKit room first.");
  const LiveKit = getLiveKitClient();
  if (!LiveKit?.Room) throw new Error("LiveKit browser client did not load.");
  const room = new LiveKit.Room({ adaptiveStream: false, dynacast: false });
  state.livekitRoom = room;
  renderLiveKitRoom("Requesting microphone");
  const RoomEvent = LiveKit.RoomEvent || {};
  const TrackKind = LiveKit.Track?.Kind || {};
  room.on(RoomEvent.Connected || "connected", () => {
    setStatus("In LiveKit");
    leaveButton.disabled = false;
    joinButton.disabled = true;
    startLiveKitStats(room);
    sendClientEvent("livekit.client.connected", { connection_state: liveKitState(room) });
  });
  room.on(RoomEvent.Disconnected || "disconnected", (reason) => {
    sendClientEvent("livekit.client.disconnected", { reason: String(reason || "") });
    stopLiveKitStats("disconnected");
    state.livekitRoom = null;
    setStatus("Left LiveKit");
  });
  room.on(RoomEvent.TrackSubscribed || "trackSubscribed", (track, publication, participant) => {
    if (track.kind !== (TrackKind.Audio || "audio")) return;
    const element = track.attach();
    element.autoplay = true;
    element.playsInline = true;
    element.volume = 1;
    element.dataset.participant = participant?.identity || "remote";
    attachAudioDiagnostics(element);
    $("#livekitAudioMount").appendChild(element);
    state.livekitAudioEls.push(element);
    state.livekitRemoteAudioTracks.push({ track, publication, participant });
    sendClientEvent("livekit.client.track_subscribed", { participant: element.dataset.participant });
    startLiveKitAudio("track_subscribed").catch((error) => {
      log("Audio unlock needed", { error: error.message });
    });
  });
  log("Joining LiveKit", { room: state.roomName });
  await room.connect(state.roomUrl, state.roomToken);
  const micPublication = await room.localParticipant.setMicrophoneEnabled(true, {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
    sampleRate: 48000,
  });
  sendClientEvent("livekit.client.microphone_enabled", {
    local_audio_publications: liveKitLocalAudioPublicationCount(room),
    publication_sid: micPublication?.trackSid || micPublication?.sid || null,
    muted: micPublication?.isMuted ?? null,
  });
  await startLiveKitAudio("join");
}

function renderLiveKitRoom(message) {
  roomMount.innerHTML = `
    <div class="placeholder">
      <div>
        <strong>LiveKit</strong><br />
        <span id="livekitStatus">${escapeHtml(message)}</span><br /><br />
        <button id="enableAudioButton" type="button">Enable Bot Audio</button>
        <div id="livekitAudioMount" class="livekit-audio-mount"></div>
      </div>
    </div>`;
  $("#enableAudioButton").addEventListener("click", () => startLiveKitAudio("button"));
}

async function startLiveKitAudio(source) {
  const room = state.livekitRoom;
  if (!room) return;
  if (typeof room.startAudio === "function") await room.startAudio();
  await Promise.allSettled(state.livekitAudioEls.map((element) => element.play()));
  sendClientEvent("browser.audio.playback", {
    source,
    remote_audio_elements: state.livekitAudioEls.length,
  });
}

function attachAudioDiagnostics(element) {
  ["playing", "waiting", "stalled", "pause", "ended", "error"].forEach((eventName) => {
    element.addEventListener(eventName, () => {
      sendClientEvent(`browser.audio.${eventName}`, {
        participant: element.dataset.participant || null,
        paused: element.paused,
        ready_state: element.readyState,
        network_state: element.networkState,
      });
    });
  });
}

function liveKitState(room) {
  return String(room?.state || room?.connectionState || "unknown");
}

function liveKitLocalAudioPublicationCount(room) {
  const publications = room?.localParticipant?.audioTrackPublications;
  if (!publications) return 0;
  if (typeof publications.size === "number") return publications.size;
  if (Array.isArray(publications)) return publications.length;
  return Object.keys(publications).length;
}

async function collectLiveKitStats(room) {
  const reports = [];
  const candidates = [
    room?.engine?.client?.pcManager?.subscriber?.pc,
    room?.engine?.client?.pcManager?.publisher?.pc,
    room?.engine?.pcManager?.subscriber?.pc,
    room?.engine?.pcManager?.publisher?.pc,
  ].filter(Boolean);
  for (const pc of candidates) {
    if (typeof pc.getStats === "function") reports.push(await pc.getStats());
  }
  let inboundPacketsLost = 0;
  let inboundPacketsReceived = 0;
  let jitterMs = null;
  let rttMs = null;
  reports.forEach((report) => {
    report.forEach((stat) => {
      const isAudio = stat.kind === "audio" || stat.mediaType === "audio";
      if (stat.type === "inbound-rtp" && isAudio) {
        inboundPacketsLost += Number(stat.packetsLost || 0);
        inboundPacketsReceived += Number(stat.packetsReceived || 0);
        if (stat.jitter !== undefined) jitterMs = Math.max(jitterMs ?? 0, Number(stat.jitter) * 1000);
      }
      if (stat.type === "candidate-pair" && (stat.selected || stat.nominated) && stat.currentRoundTripTime !== undefined) {
        rttMs = Math.max(rttMs ?? 0, Number(stat.currentRoundTripTime) * 1000);
      }
    });
  });
  const total = inboundPacketsLost + inboundPacketsReceived;
  return {
    connection_state: liveKitState(room),
    remote_audio_tracks: state.livekitRemoteAudioTracks.length,
    inbound_packets_lost: inboundPacketsLost,
    inbound_packet_loss_pct: total ? Math.round((inboundPacketsLost / total) * 1000) / 10 : null,
    jitter_ms: jitterMs === null ? null : Math.round(jitterMs),
    rtt_ms: rttMs === null ? null : Math.round(rttMs),
  };
}

function startLiveKitStats(room) {
  stopLiveKitStats();
  state.livekitStatsTimer = window.setInterval(async () => {
    if (!state.livekitRoom) return;
    sendClientEvent("livekit.client.stats", await collectLiveKitStats(room));
  }, 3000);
}

function stopLiveKitStats(reason = "stopped") {
  if (state.livekitStatsTimer) window.clearInterval(state.livekitStatsTimer);
  state.livekitStatsTimer = null;
  if (state.callId) sendClientEvent("livekit.client.stats_stopped", { reason });
}

function humeMimeType() {
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]
    .find((type) => window.MediaRecorder?.isTypeSupported?.(type)) || "";
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result || "").split(",").pop());
    reader.onerror = () => reject(reader.error || new Error("Blob read failed"));
    reader.readAsDataURL(blob);
  });
}

function base64ToBlob(data, mimeType = "audio/wav") {
  const binary = window.atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mimeType });
}

function humeSocketUrl(session) {
  const url = new URL(session.chat_endpoint);
  url.searchParams.set("access_token", session.access_token);
  if (session.config_id) url.searchParams.set("config_id", session.config_id);
  if (session.config_version !== null && session.config_version !== undefined) {
    url.searchParams.set("config_version", String(session.config_version));
  }
  if (session.session_settings) url.searchParams.set("session_settings", JSON.stringify(session.session_settings));
  url.searchParams.set("verbose_transcription", session.verbose_transcription === false ? "false" : "true");
  return url.toString();
}

async function joinHume() {
  if (!state.humeSession) throw new Error("Create a Hume session first.");
  const socket = new WebSocket(humeSocketUrl(state.humeSession));
  state.humeSocket = socket;
  renderPlaceholder("Connecting Hume");
  socket.onopen = async () => {
    setStatus("In Hume");
    leaveButton.disabled = false;
    joinButton.disabled = true;
    sendClientEvent("hume.client.connected", { config_id: state.humeSession.config_id || "default" });
    if (state.humeSession.session_settings) {
      socket.send(JSON.stringify(state.humeSession.session_settings));
      sendClientEvent("hume.client.session_settings_sent", {
        config_id: state.humeSession.config_id || "default",
      });
    }
    await startHumeRecorder(socket);
  };
  socket.onmessage = (event) => {
    try {
      handleHumeMessage(JSON.parse(event.data));
    } catch (error) {
      sendClientEvent("hume.client.message_parse_error", { error_message: error.message });
    }
  };
  socket.onerror = () => sendClientEvent("hume.client.socket_error", {});
  socket.onclose = (event) => disconnectHume("socket_closed", { close_code: event.code });
}

async function startHumeRecorder(socket) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    video: false,
  });
  const mimeType = humeMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  recorder.ondataavailable = async (event) => {
    if (!event.data?.size || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "audio_input", data: await blobToBase64(event.data) }));
  };
  recorder.start(100);
  state.humeMicStream = stream;
  state.humeRecorder = recorder;
  sendClientEvent("hume.client.audio_capture_started", { audio_mime_type: mimeType || "browser-default" });
}

function handleHumeMessage(message) {
  const type = message?.type || "unknown";
  const text = message?.message?.content || message?.message?.text || message?.content || message?.text || message?.transcript || "";
  if (type === "audio_output" && message.data) {
    const receivedAt = performance.now();
    state.humeAudioQueue.push({ blob: base64ToBlob(message.data), receivedAt });
    sendClientEvent("hume.client.audio_output", { audio_queue_depth: state.humeAudioQueue.length });
    playNextHumeAudio();
    return;
  }
  if (type === "user_message") {
    state.humeLastUserAt = performance.now();
    stopHumeAudio("user_message");
  }
  sendClientEvent(`hume.client.${String(type).replace(/[^a-zA-Z0-9]+/g, "_").toLowerCase()}`, {
    transcript: text || undefined,
    text_preview: text ? text.slice(0, 160) : undefined,
  });
}

function playNextHumeAudio() {
  if (state.humeAudioPlaying || !state.humeAudioQueue.length) return;
  const item = state.humeAudioQueue.shift();
  const audio = new Audio(URL.createObjectURL(item.blob));
  state.humeAudioPlaying = true;
  state.humeCurrentAudio = audio;
  audio.onplaying = () => {
    sendClientEvent("hume.client.first_audio_playing", {
      playback_delay_ms: Math.round(performance.now() - item.receivedAt),
      hume_latency_ms: state.humeLastUserAt ? Math.round(performance.now() - state.humeLastUserAt) : null,
    });
  };
  audio.onended = () => {
    state.humeAudioPlaying = false;
    state.humeCurrentAudio = null;
    playNextHumeAudio();
  };
  audio.onerror = () => {
    state.humeAudioPlaying = false;
    state.humeCurrentAudio = null;
    sendClientEvent("hume.client.audio_playback_error", {});
    playNextHumeAudio();
  };
  audio.play().catch((error) => {
    state.humeAudioPlaying = false;
    state.humeCurrentAudio = null;
    sendClientEvent("hume.client.audio_autoplay_blocked", { error_message: error.message });
  });
}

function stopHumeAudio(reason) {
  state.humeAudioQueue = [];
  if (state.humeCurrentAudio) {
    state.humeCurrentAudio.pause();
    state.humeCurrentAudio = null;
  }
  state.humeAudioPlaying = false;
  if (state.callId) sendClientEvent("hume.client.audio_stopped", { reason });
}

function disconnectHume(reason = "leave", metadata = {}) {
  if (state.humeRecorder && state.humeRecorder.state !== "inactive") state.humeRecorder.stop();
  state.humeRecorder = null;
  if (state.humeMicStream) state.humeMicStream.getTracks().forEach((track) => track.stop());
  state.humeMicStream = null;
  stopHumeAudio(reason);
  if (state.humeSocket && state.humeSocket.readyState <= WebSocket.OPEN) state.humeSocket.close();
  state.humeSocket = null;
  if (state.callId && state.transport === "hume_evi") sendClientEvent("hume.client.disconnected", { reason, ...metadata });
}

async function sendClientEvent(eventName, metadata = {}) {
  if (!state.callId) return;
  try {
    await postJson("/api/analytics/client-event", {
      call_id: state.callId,
      session_id: state.sessionId,
      event_name: eventName,
      provider: "browser",
      metadata,
    });
  } catch {
    // Metrics should never break the call path.
  }
}

function startPolling() {
  if (state.metricsTimer) return;
  state.metricsTimer = window.setInterval(refreshMetrics, 1500);
  refreshMetrics();
}

async function refreshMetrics() {
  try {
    const summaryUrl = state.callId
      ? `/api/analytics/summary?call_id=${encodeURIComponent(state.callId)}`
      : "/api/analytics/summary";
    const summary = await fetch(summaryUrl).then((response) => response.json());
    const metricsCallId = state.callId || summary.latest_call_id || summary.call_id;
    const transcript = metricsCallId
      ? await fetch(`/api/analytics/transcript?call_id=${encodeURIComponent(metricsCallId)}`).then((response) => response.json())
      : { items: [] };
    const callNotes = metricsCallId
      ? await fetch(`/api/analytics/call-notes?call_id=${encodeURIComponent(metricsCallId)}`).then((response) => response.json())
      : null;
    $("#metricAvg").textContent = ms(summary.avg_perceived_latency_ms);
    $("#metricP95").textContent = ms(summary.p95_perceived_latency_ms);
    $("#metricStt").textContent = ms(summary.avg_stt_processing_ms ?? summary.avg_speech_to_transcript_ms);
    $("#metricTtft").textContent = ms(summary.avg_provider_ttft_ms);
    $("#metricTts").textContent = ms(summary.avg_tts_first_audio_ms);
    $("#metricPlayback").textContent = ms(summary.avg_playback_delay_ms);
    $("#metricErrors").textContent = String(summary.errors || 0);
    if (!state.callId && metricsCallId) {
      callIdLabel.textContent = metricsCallId;
    }
    $("#configLine").textContent = `${summary.transport_provider || state.transport} · ${summary.stt_provider || state.sttProvider}/${summary.stt_model || state.sttModel} · ${summary.llm_provider || state.llmProvider}/${summary.llm_model || state.llmModel}`;
    if (summary.tool_call_count || summary.tools_enabled) {
      $("#configLine").textContent += ` · tools=${summary.tools_enabled ? "on" : "off"} calls=${summary.tool_call_count || 0}`;
    }
    renderToolTerminalEvents(summary.latest_events || []);
    const stats = summary.livekit_client_stats || {};
    $("#networkLine").textContent = stats.connection_state
      ? `network loss=${stats.inbound_packet_loss_pct ?? "n/a"}% jitter=${stats.jitter_ms ?? "n/a"}ms rtt=${stats.rtt_ms ?? "n/a"}ms`
      : "";
    renderTranscript(transcript.items || []);
    renderCallNotes(callNotes);
  } catch (error) {
    log("Metrics failed", { error: error.message });
  }
}

function renderCallNotes(notes) {
  if (!notes) {
    callNotesOutput.textContent = "Generated notes will appear after transcript or tool activity.";
    return;
  }
  callNotesOutput.textContent = notes.notes_text || "Call notes will appear here after the call.";
}

function renderToolTerminalEvents(events) {
  events.forEach((event) => {
    const eventName = String(event.event_name || "").replaceAll("_", ".");
    if (!["tool.call.started", "tool.call.completed", "tool.call.failed"].includes(eventName)) return;
    const metadata = event.metadata || {};
    const toolName = metadata.tool_name || "tool";
    const outcome = metadata.outcome || (eventName.endsWith(".started") ? "started" : "");
    const key = `${event.timestamp_wall_iso}|${eventName}|${toolName}|${outcome}`;
    if (state.toolEventKeys.has(key)) return;
    state.toolEventKeys.add(key);
    if (eventName === "tool.call.started") {
      log("Tool started", { tool: toolName });
      return;
    }
    if (eventName === "tool.call.completed") {
      const completeMessage = String(outcome).includes("confirmation_required")
        ? "Tool needs confirmation"
        : "Tool succeeded";
      log(completeMessage, {
        tool: toolName,
        outcome,
        duration_ms: metadata.duration_ms ?? null,
      });
      return;
    }
    log("Tool failed", {
      tool: toolName,
      outcome,
      duration_ms: metadata.duration_ms ?? null,
    });
  });
}

function renderTranscript(items) {
  transcriptList.innerHTML = "";
  items.slice(-40).forEach((item) => {
    const div = document.createElement("div");
    div.className = "transcript-item";
    const role = item.event_name === "transcript.user" ? "User" : "Assistant";
    const text = item.metadata?.text || item.metadata?.text_preview || "";
    div.innerHTML = `<span>${role}</span>${escapeHtml(text)}`;
    transcriptList.appendChild(div);
  });
  transcriptList.scrollTop = transcriptList.scrollHeight;
}

prepareButton.addEventListener("click", () => prepare().catch((error) => {
  setStatus("Prepare failed");
  log("Prepare failed", { error: error.message });
}));

startAgentButton.addEventListener("click", () => startAgent().catch((error) => {
  setStatus("Agent failed");
  log("Agent failed", { error: error.message });
}));

joinButton.addEventListener("click", () => join().catch((error) => {
  setStatus("Join failed");
  log("Join failed", { error: error.message });
}));

leaveButton.addEventListener("click", () => leaveCurrent().catch((error) => log("Leave failed", { error: error.message })));

stopAgentButton.addEventListener("click", async () => {
  const result = await postJson("/api/agent/stop", {});
  log("Agent stop", result);
});

clientIdInput.addEventListener("change", () => {
  syncToolStateFromInputs();
  refreshIntegrationStatus().catch((error) => log("Integration status failed", { error: error.message }));
});

callerPhoneInput.addEventListener("change", () => {
  syncToolStateFromInputs();
  log("Caller phone updated", { configured: Boolean(state.callerPhone) });
});

knowledgeBaseInput.addEventListener("change", () => {
  syncToolStateFromInputs();
  log("Call KB updated", { chars: state.knowledgeBase.length });
});

refreshCallNotesButton.addEventListener("click", () => refreshMetrics().catch((error) => log("Call notes refresh failed", { error: error.message })));

toolsEnabledInput.addEventListener("change", () => {
  syncToolStateFromInputs();
  log("Tools toggled", { client_id: state.clientId, tools_enabled: state.toolsEnabled });
});

connectCalendarButton.addEventListener("click", () => connectCalendar().catch((error) => {
  log("Calendar connect failed", { error: error.message });
  integrationStatusLine.textContent = error.message;
}));

integrationStatusButton.addEventListener("click", () => refreshIntegrationStatus().catch((error) => {
  log("Integration status failed", { error: error.message });
  integrationStatusLine.textContent = error.message;
}));

loadConfig().catch((error) => {
  setStatus("Config failed");
  log("Config failed", { error: error.message });
});
