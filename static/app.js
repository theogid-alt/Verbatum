const state = {
  transport: "livekit",
  sttProvider: "deepgram",
  sttModel: "nova-3-general",
  llmProvider: "groq",
  llmModel: "llama-3.1-8b-instant",
  clientId: "demo",
  callerPhone: "",
  knowledgeBase: "",
  systemPrompt: "",
  clientConfig: null,
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
  metricsCallId: null,
  evaluationContext: null,
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
const businessNameInput = $("#businessNameInput");
const assistantNameInput = $("#assistantNameInput");
const industryInput = $("#industryInput");
const timezoneInput = $("#timezoneInput");
const greetingInput = $("#greetingInput");
const systemPromptInput = $("#systemPromptInput");
const knowledgeBaseInput = $("#knowledgeBaseInput");
const saveProfileButton = $("#saveProfileButton");
const savePromptButton = $("#savePromptButton");
const saveKbButton = $("#saveKbButton");
const resetClientKitButton = $("#resetClientKitButton");
const clientProfileLine = $("#clientProfileLine");
const integrationCards = $("#integrationCards");
const integrationCountLine = $("#integrationCountLine");
const callNotesOutput = $("#callNotesOutput");
const refreshCallNotesButton = $("#refreshCallNotesButton");
const evaluateCallButton = $("#evaluateCallButton");
const saveEvaluationButton = $("#saveEvaluationButton");
const evaluationStatusLine = $("#evaluationStatusLine");
const evaluationOverall = $("#evaluationOverall");
const evaluationNeedsAttention = $("#evaluationNeedsAttention");
const evaluationSavedState = $("#evaluationSavedState");
const evaluationVersionInput = $("#evaluationVersionInput");
const evaluationVersionSummary = $("#evaluationVersionSummary");
const evaluationAutoMetrics = $("#evaluationAutoMetrics");
const evaluationFields = $("#evaluationFields");
const evaluationNotesInput = $("#evaluationNotesInput");
const DEFAULT_EVALUATION_VERSION = "v0.3";
const toolsEnabledInput = $("#toolsEnabledInput");
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

async function putJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "PUT",
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
  const readyToolCards = integrationCardsForTools().filter((card) => card.enabled && card.ready);
  const toolsCompatible = state.transport !== "hume_evi" && state.llmProvider !== "ultravox";
  const toolsReady = toolsCompatible && readyToolCards.length > 0;
  toolsEnabledInput.disabled = !toolsReady;
  if (!toolsReady) {
    toolsEnabledInput.checked = false;
    state.toolsEnabled = false;
  } else if (state.config?.tools_enabled) {
    toolsEnabledInput.checked = true;
    state.toolsEnabled = true;
  }
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
  state.metricsCallId = null;
  state.evaluationContext = null;
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

function hydrateClientEditor() {
  const profile = state.clientConfig?.profile || {};
  clientIdInput.value = profile.profile_id || state.clientId || "demo";
  businessNameInput.value = profile.business_name || "";
  assistantNameInput.value = profile.assistant_name || "";
  industryInput.value = profile.industry || "";
  timezoneInput.value = profile.timezone || "";
  greetingInput.value = profile.greeting || "";
  systemPromptInput.value = state.systemPrompt || "";
  knowledgeBaseInput.value = state.knowledgeBase || "";
  clientProfileLine.textContent = `${profile.business_name || "Local client"} · ${profile.industry || "industry unset"} · ${profile.timezone || "timezone unset"}`;
}

function applyStackFromProfile(profile = {}) {
  state.transport = profile.transport_provider || state.config?.transport_provider || state.transport || "livekit";
  state.sttProvider = profile.stt_provider || state.config?.stt_provider || state.sttProvider || "deepgram";
  state.sttModel = profile.deepgram_model || state.config?.stt_model || state.sttModel || "nova-3-general";
  state.llmProvider = profile.llm_provider || state.config?.llm_provider || state.llmProvider || "groq";
  state.llmModel = profile.llm_model || state.config?.llm_model || state.llmModel || "llama-3.1-8b-instant";
}

async function loadConfig() {
  const response = await fetch("/api/config");
  state.config = await response.json();
  state.clientConfig = state.config.client_config || null;
  state.transport = state.config.transport_provider || "livekit";
  state.sttProvider = state.config.stt_provider || "deepgram";
  state.sttModel = state.config.stt_model || "nova-3-general";
  state.llmProvider = state.config.llm_provider || "groq";
  state.llmModel = state.config.llm_model || "llama-3.1-8b-instant";
  applyStackFromProfile(state.clientConfig?.profile || {});
  state.clientId = state.config.default_client_id || "demo";
  state.callerPhone = state.config.caller_phone || "";
  state.systemPrompt = state.clientConfig?.prompt?.content || "";
  state.knowledgeBase = state.clientConfig?.knowledge_base?.content || state.config.knowledge_base || "";
  state.toolsEnabled = Boolean(state.config.tools_enabled);
  hydrateClientEditor();
  callerPhoneInput.value = state.callerPhone;
  toolsEnabledInput.checked = state.toolsEnabled;
  renderIntegrationCards();
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
    system_prompt: state.systemPrompt,
    tools_enabled: state.toolsEnabled && state.transport !== "hume_evi" && state.llmProvider !== "ultravox",
  };
}

async function prepare() {
  syncToolStateFromInputs();
  if (state.transport === "hume_evi") {
    const session = await postJson("/api/hume/evi/session", {
      knowledge_base: state.knowledgeBase,
      system_prompt: state.systemPrompt,
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
  state.systemPrompt = state.clientConfig?.prompt?.content || state.systemPrompt || "";
  state.knowledgeBase = state.clientConfig?.knowledge_base?.content || state.knowledgeBase || "";
  state.toolsEnabled = Boolean(toolsEnabledInput.checked);
}

async function connectCalendar() {
  syncToolStateFromInputs();
  const card = integrationCardById("google_calendar") || { id: "google_calendar", integration_key: currentCalendarIntegrationKey(), label: "Google Calendar" };
  return connectNangoIntegration(card);
}

async function connectNangoIntegration(card) {
  syncToolStateFromInputs();
  const result = await postJson("/api/integrations/nango/connect-session", {
    client_id: state.clientId,
    integration_id: card.id,
    integration_key: card.integration_key,
  });
  integrationStatusLine.textContent = `${card.label} connect link expires ${result.expires_at || "soon"}`;
  log("Nango connect session created", {
    client_id: result.client_id,
    integration_id: result.integration_id,
    integration_key: result.integration_key,
  });
  window.open(result.connect_link, "_blank", "noopener");
  startIntegrationStatusPolling();
}

async function connectIntegration(integrationId) {
  const card = integrationCardById(integrationId);
  if (card?.provider === "nango") return connectNangoIntegration(card);
  log("Integration connect unavailable", { integration_id: integrationId });
}

async function refreshIntegrationStatus() {
  syncToolStateFromInputs();
  const response = await fetch(`/api/integrations/status?client_id=${encodeURIComponent(state.clientId)}`);
  const status = await response.json();
  if (!response.ok) throw new Error(status.detail || `HTTP ${response.status}`);
  if (status.cards) {
    state.config.integration_catalog.cards = status.cards;
  }
  renderIntegrationCards();
  state.integrationConnected = allIntegrationCards().some((card) => card.provider === "nango" && card.enabled && card.ready);
  const readyToolCards = integrationCardsForTools().filter((card) => card.enabled && card.ready);
  if (readyToolCards.length && state.config?.tools_enabled && state.transport !== "hume_evi" && state.llmProvider !== "ultravox") {
    state.toolsEnabled = true;
    toolsEnabledInput.checked = true;
  }
  integrationStatusLine.textContent = readyToolCards.length
    ? `Ready tools: ${readyToolCards.map((card) => card.label).join(", ")}`
    : "No enabled integrations are ready yet.";
  renderControls();
  if (state.integrationConnected) stopIntegrationStatusPolling();
  return status;
}

function startIntegrationStatusPolling() {
  stopIntegrationStatusPolling();
  let attempts = 0;
  integrationStatusLine.textContent = "Waiting for integration connection...";
  state.integrationPollTimer = window.setInterval(() => {
    attempts += 1;
    refreshIntegrationStatus().catch((error) => {
      log("Integration status failed", { error: error.message });
    });
    if (attempts >= 40) {
      stopIntegrationStatusPolling();
      if (!state.integrationConnected) {
        integrationStatusLine.textContent = "Integration still not connected. Finish Nango auth, then click Status.";
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
  return integrationCardById("google_calendar")?.integration_key || "google-calendar";
}

function allIntegrationCards() {
  return state.config?.integration_catalog?.cards || [];
}

function integrationCardById(integrationId) {
  return allIntegrationCards().find((card) => card.id === integrationId);
}

function integrationCardsForTools() {
  return allIntegrationCards().filter((card) => Array.isArray(card.allowed_tools) && card.allowed_tools.length);
}

function renderIntegrationCards() {
  if (!integrationCards) return;
  const cards = allIntegrationCards();
  const readyCount = cards.filter((card) => card.enabled && card.ready).length;
  integrationCountLine.textContent = `${readyCount} ready · ${cards.length} slots`;
  integrationCards.innerHTML = "";
  cards.forEach((card) => {
    const element = document.createElement("article");
    element.className = `integration-card ${card.enabled ? "" : "disabled"}`;
    const logoFallback = (card.label || "?").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    const envText = card.missing_env?.length ? `Needs: ${card.missing_env.join(", ")}` : (card.required_env?.length ? `Env: ${card.required_env.join(", ")}` : "");
    element.innerHTML = `
      <div class="integration-top">
        <div class="integration-logo">
          <img src="${escapeHtml(card.logo_path || "")}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'), {textContent: '${escapeHtml(logoFallback)}'}))" />
        </div>
        <div class="integration-title">
          <strong>${escapeHtml(card.label)}</strong>
          <span>${escapeHtml(card.status_label || card.status)}</span>
        </div>
      </div>
      <p>${escapeHtml(card.description || "")}</p>
      <div class="integration-env">${escapeHtml(envText)}</div>
      <div class="integration-actions"></div>
    `;
    const actions = element.querySelector(".integration-actions");
    if (card.implemented) {
      if (card.provider === "nango" && card.enabled && !card.ready && card.status !== "missing_env") {
        actions.appendChild(cardButton("Connect", () => connectIntegration(card.id)));
      }
      actions.appendChild(cardButton("Test", () => testIntegration(card.id), !card.enabled));
      actions.appendChild(cardButton(card.enabled ? "Disconnect" : "Enable", () => {
        if (card.enabled) {
          disconnectIntegration(card.id);
        } else {
          setIntegrationEnabled(card.id, true);
        }
      }));
    } else {
      actions.appendChild(cardButton("Coming soon", () => {}, true));
    }
    integrationCards.appendChild(element);
  });
}

function cardButton(label, onClick, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener("click", onClick);
  return button;
}

async function reloadClientConfig() {
  const response = await fetch("/api/client-config");
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  state.clientConfig = data;
  state.config.client_config = data;
  state.config.integration_catalog = data.integration_catalog;
  state.clientId = data.profile?.profile_id || state.clientId;
  state.systemPrompt = data.prompt?.content || "";
  state.knowledgeBase = data.knowledge_base?.content || "";
  hydrateClientEditor();
  renderIntegrationCards();
  renderControls();
  return data;
}

async function saveProfile() {
  const payload = {
    business_name: businessNameInput.value,
    assistant_name: assistantNameInput.value,
    industry: industryInput.value,
    timezone: timezoneInput.value,
    greeting: greetingInput.value,
    transport_provider: state.transport,
    stt_provider: state.sttProvider,
    deepgram_model: state.sttModel,
    llm_provider: state.llmProvider,
    llm_model: state.llmModel,
  };
  const data = await putJson("/api/client-config/profile", payload);
  state.clientConfig = data;
  state.config.client_config = data;
  state.config.integration_catalog = data.integration_catalog;
  state.clientId = data.profile?.profile_id || state.clientId;
  hydrateClientEditor();
  renderIntegrationCards();
  log("Client profile saved", { business: payload.business_name, stack: `${state.transport}/${state.sttModel}/${state.llmProvider}` });
}

async function savePrompt() {
  const data = await putJson("/api/client-config/prompt", { content: systemPromptInput.value });
  state.clientConfig = data;
  state.config.client_config = data;
  state.systemPrompt = data.prompt?.content || "";
  hydrateClientEditor();
  log("Prompt saved", { chars: state.systemPrompt.length });
}

async function saveKb() {
  const data = await putJson("/api/client-config/kb", { content: knowledgeBaseInput.value });
  state.clientConfig = data;
  state.config.client_config = data;
  state.knowledgeBase = data.knowledge_base?.content || "";
  hydrateClientEditor();
  log("Knowledge base saved", { chars: state.knowledgeBase.length });
}

async function resetClientKit() {
  if (!window.confirm("Reset the client profile, system prompt, and persistent KB to the current baseline? Integrations stay connected.")) {
    return;
  }
  const data = await postJson("/api/client-config/reset", {});
  state.clientConfig = data;
  state.config.client_config = data;
  state.config.integration_catalog = data.integration_catalog;
  state.systemPrompt = data.prompt?.content || "";
  state.knowledgeBase = data.knowledge_base?.content || "";
  applyStackFromProfile(data.profile || {});
  hydrateClientEditor();
  renderIntegrationCards();
  renderControls();
  log("Client kit reset", {
    stack: `${state.transport}/${state.sttModel}/${state.llmProvider}/${state.llmModel}`,
    prompt_chars: state.systemPrompt.length,
    kb_chars: state.knowledgeBase.length,
  });
}

async function setIntegrationEnabled(integrationId, enabled) {
  const data = await putJson("/api/client-config/integrations", {
    integrations: { [integrationId]: { enabled } },
  });
  state.clientConfig = data;
  state.config.client_config = data;
  state.config.integration_catalog = data.integration_catalog;
  renderIntegrationCards();
  renderControls();
  log("Integration updated", { integration_id: integrationId, enabled });
}

async function disconnectIntegration(integrationId) {
  const data = await postJson(`/api/integrations/${encodeURIComponent(integrationId)}/disconnect`, {});
  state.clientConfig = data;
  state.config.client_config = data;
  state.config.integration_catalog = data.integration_catalog;
  renderIntegrationCards();
  renderControls();
  log("Integration disconnected", { integration_id: integrationId });
}

async function testIntegration(integrationId) {
  const result = await postJson(`/api/integrations/${encodeURIComponent(integrationId)}/test`, {});
  log(result.ok ? "Integration test passed" : "Integration test failed", {
    integration_id: integrationId,
    status: result.status,
    message: result.message,
  });
  integrationStatusLine.textContent = result.message || result.status || "Integration test complete";
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
    state.metricsCallId = metricsCallId || null;
    const transcript = metricsCallId
      ? await fetch(`/api/analytics/transcript?call_id=${encodeURIComponent(metricsCallId)}`).then((response) => response.json())
      : { items: [] };
    const callNotes = metricsCallId
      ? await fetch(`/api/analytics/call-notes?call_id=${encodeURIComponent(metricsCallId)}`).then((response) => response.json())
      : null;
    $("#metricAvg").textContent = ms(summary.avg_clean_perceived_latency_ms ?? summary.avg_perceived_latency_ms);
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
      if (summary.p95_normal_perceived_latency_ms || summary.p95_tool_perceived_latency_ms) {
        $("#configLine").textContent += ` · normal p95=${ms(summary.p95_normal_perceived_latency_ms)} tool p95=${ms(summary.p95_tool_perceived_latency_ms)}`;
      }
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

async function evaluateCurrentCall() {
  const callId = state.callId || state.metricsCallId;
  if (!callId) {
    log("Evaluation skipped", { reason: "No call_id available" });
    evaluationStatusLine.textContent = "Create or select a call before evaluating.";
    return;
  }
  const botVersion = sanitizeBotVersion(evaluationVersionInput?.value || DEFAULT_EVALUATION_VERSION);
  const context = await fetch(`/api/evaluations/call?call_id=${encodeURIComponent(callId)}&bot_version=${encodeURIComponent(botVersion)}`).then((response) => response.json());
  state.evaluationContext = context;
  renderEvaluationContext(context);
  await refreshEvaluationVersionSummary();
  log("Evaluation loaded", {
    call_id: context.call_id,
    bot_version: context.bot_version,
    saved: Boolean(context.saved_evaluation),
  });
}

function renderEvaluationContext(context) {
  const saved = context.saved_evaluation || null;
  const summary = saved?.score_summary || {};
  const botVersion = saved?.bot_version || context.bot_version || sanitizeBotVersion(evaluationVersionInput?.value || DEFAULT_EVALUATION_VERSION);
  if (evaluationVersionInput) evaluationVersionInput.value = botVersion;
  evaluationStatusLine.textContent = `Call ${context.call_id || "n/a"} · ${botVersion} · ${context.transcript?.length || 0} transcript items · ${context.call_notes?.status || "waiting"}`;
  evaluationSavedState.textContent = saved ? "Yes" : "No";
  evaluationOverall.textContent = summary.overall_average ?? "n/a";
  evaluationNeedsAttention.textContent = String(summary.needs_attention?.length || 0);
  evaluationNotesInput.value = saved?.reviewer_notes || "";
  renderEvaluationAutoMetrics({ ...(saved?.auto_metrics || {}), ...(context.auto_metrics || {}) });
  renderEvaluationFields(context.rubric || {}, saved?.scores || {});
  saveEvaluationButton.disabled = !context.call_id;
  updateEvaluationPreview();
}

function renderEvaluationAutoMetrics(metrics) {
  const stats = metrics.livekit_client_stats || {};
  const cards = [
    ["Avg", ms(metrics.avg_clean_perceived_latency_ms ?? metrics.avg_perceived_latency_ms)],
    ["P95", ms(metrics.p95_perceived_latency_ms)],
    ["Raw avg", ms(metrics.avg_perceived_latency_ms)],
    ["Peaks", `${metrics.peak_turn_count || 0} > ${ms(metrics.latency_peak_threshold_ms || 2000)}`],
    ["Normal p95", ms(metrics.p95_normal_perceived_latency_ms)],
    ["Tool p95", ms(metrics.p95_tool_perceived_latency_ms)],
    ["Max", ms(metrics.max_perceived_latency_ms)],
    ["STT avg", ms(metrics.avg_stt_processing_ms ?? metrics.avg_speech_to_transcript_ms)],
    ["STT p95", ms(metrics.p95_stt_processing_ms ?? metrics.p95_speech_to_transcript_ms)],
    ["TTFT avg", ms(metrics.avg_provider_ttft_ms)],
    ["TTFT p95", ms(metrics.p95_provider_ttft_ms)],
    ["TTS avg", ms(metrics.avg_tts_first_audio_ms)],
    ["TTS p95", ms(metrics.p95_tts_first_audio_ms)],
    ["Playback", ms(metrics.avg_playback_delay_ms)],
    ["Transcript→LLM", ms(metrics.avg_transcript_to_llm_ms)],
    ["Tools", `${metrics.tool_call_count || 0} calls · ${metrics.tool_failed_count || 0} failed · ${metrics.tool_turn_count || 0} turns`],
    ["Tool duration", ms(metrics.avg_tool_duration_ms)],
    ["Network", stats.connection_state ? `${stats.inbound_packet_loss_pct ?? "n/a"}% loss · ${stats.jitter_ms ?? "n/a"}ms jitter` : "n/a"],
  ];
  evaluationAutoMetrics.innerHTML = cards.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
}

function renderEvaluationFields(rubric, savedScores) {
  const fields = rubric.fields || [];
  evaluationFields.innerHTML = "";
  fields.forEach((field) => {
    const saved = savedScores[field.id] || {};
    const article = document.createElement("article");
    article.className = "evaluation-field";
    article.dataset.evalField = field.id;
    article.innerHTML = `
      <label>${escapeHtml(field.label)}</label>
      <p>${escapeHtml(field.description || "")}</p>
      <select data-eval-score="${escapeHtml(field.id)}">
        <option value="">Score 1-5</option>
        <option value="5">5 · Excellent</option>
        <option value="4">4 · Good</option>
        <option value="3">3 · Usable</option>
        <option value="2">2 · Needs attention</option>
        <option value="1">1 · Failed</option>
      </select>
      <textarea rows="2" data-eval-note="${escapeHtml(field.id)}" placeholder="Optional note for ${escapeHtml(field.label)}"></textarea>
    `;
    const select = article.querySelector("select");
    const note = article.querySelector("textarea");
    select.value = saved.score ? String(saved.score) : "";
    note.value = saved.notes || "";
    select.addEventListener("change", updateEvaluationPreview);
    note.addEventListener("input", updateEvaluationPreview);
    evaluationFields.appendChild(article);
  });
}

function evaluationPayloadFromForm() {
  const scores = {};
  evaluationFields.querySelectorAll("[data-eval-field]").forEach((field) => {
    const fieldId = field.dataset.evalField;
    const score = field.querySelector(`[data-eval-score="${CSS.escape(fieldId)}"]`)?.value || null;
    const notes = field.querySelector(`[data-eval-note="${CSS.escape(fieldId)}"]`)?.value || "";
    scores[fieldId] = { score, notes };
  });
  return {
    bot_version: sanitizeBotVersion(evaluationVersionInput?.value || DEFAULT_EVALUATION_VERSION),
    scores,
    reviewer_notes: evaluationNotesInput.value || "",
  };
}

function updateEvaluationPreview() {
  const values = Object.values(evaluationPayloadFromForm().scores)
    .map((item) => Number(item.score))
    .filter((score) => Number.isFinite(score) && score > 0);
  const needsAttention = values.filter((score) => score <= 2).length;
  evaluationOverall.textContent = values.length ? (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2) : "n/a";
  evaluationNeedsAttention.textContent = String(needsAttention);
}

async function saveEvaluation() {
  const callId = state.evaluationContext?.call_id || state.callId || state.metricsCallId;
  if (!callId) {
    throw new Error("No call_id available for evaluation.");
  }
  const report = await putJson(`/api/evaluations/call/${encodeURIComponent(callId)}`, evaluationPayloadFromForm());
  state.evaluationContext = {
    ...(state.evaluationContext || {}),
    call_id: callId,
    bot_version: report.bot_version,
    saved_evaluation: report,
  };
  evaluationSavedState.textContent = "Yes";
  evaluationStatusLine.textContent = `Saved evaluation for ${callId} · ${report.bot_version || DEFAULT_EVALUATION_VERSION}`;
  await refreshEvaluationVersionSummary();
  log("Evaluation saved", {
    call_id: callId,
    bot_version: report.bot_version,
    overall_average: report.score_summary?.overall_average ?? null,
    needs_attention: report.score_summary?.needs_attention?.length || 0,
  });
}

async function refreshEvaluationVersionSummary() {
  if (!evaluationVersionSummary) return;
  try {
    const summary = await fetch("/api/evaluations/summary").then((response) => response.json());
    const version = sanitizeBotVersion(evaluationVersionInput?.value || DEFAULT_EVALUATION_VERSION);
    const selected = (summary.versions || []).find((item) => item.bot_version === version);
    if (!selected) {
      evaluationVersionSummary.textContent = `${version}: no saved evaluations yet`;
      return;
    }
    const domainText = Object.entries(selected.domain_averages || {})
      .slice(0, 5)
      .map(([key, value]) => `${key} ${value ?? "n/a"}`)
      .join(" · ");
    evaluationVersionSummary.textContent = `${version}: ${selected.evaluation_count} evals · avg ${selected.overall_average ?? "n/a"}${domainText ? ` · ${domainText}` : ""}`;
  } catch (error) {
    evaluationVersionSummary.textContent = `Evaluation summary unavailable: ${error.message}`;
  }
}

function sanitizeBotVersion(value) {
  const cleaned = String(value || DEFAULT_EVALUATION_VERSION).trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-._]+|[-._]+$/g, "");
  return cleaned || DEFAULT_EVALUATION_VERSION;
}

function renderToolTerminalEvents(events) {
  events.forEach((event) => {
    const eventName = String(event.event_name || "").replaceAll("_", ".");
    const visibleToolEvents = [
      "tool.call.started",
      "tool.call.completed",
      "tool.call.failed",
      "tool.confirmation.required",
      "tool.confirmation.accepted",
      "tool.confirmation.rejected",
      "tool.direct.activated",
      "tool.direct.skipped",
    ];
    if (!visibleToolEvents.includes(eventName)) return;
    const metadata = event.metadata || {};
    const toolName = metadata.tool_name || "tool";
    const outcome = metadata.outcome || (eventName.endsWith(".started") ? "started" : "");
    const key = `${event.timestamp_wall_iso}|${eventName}|${toolName}|${outcome}`;
    if (state.toolEventKeys.has(key)) return;
    state.toolEventKeys.add(key);
    const facts = compactToolFacts(metadata);
    if (eventName === "tool.direct.activated") {
      log("Tool direct action", { tool: toolName, ...facts });
      return;
    }
    if (eventName === "tool.direct.skipped") {
      log("Tool skipped", { tool: toolName, outcome, ...facts });
      return;
    }
    if (eventName === "tool.call.started") {
      log("Tool started", { tool: toolName });
      return;
    }
    if (eventName === "tool.confirmation.required") {
      log("Tool confirmation required", { tool: toolName, outcome, ...facts });
      return;
    }
    if (eventName === "tool.confirmation.accepted" || eventName === "tool.confirmation.rejected") {
      log(eventName.endsWith(".accepted") ? "Tool confirmation accepted" : "Tool confirmation rejected", {
        tool: toolName,
        outcome,
        ...facts,
      });
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
        ...facts,
      });
      return;
    }
    log("Tool failed", {
      tool: toolName,
      outcome,
      duration_ms: metadata.duration_ms ?? null,
      ...facts,
    });
  });
}

function compactToolFacts(metadata) {
  const keys = [
    "ok",
    "booking_booked",
    "booking_prepared",
    "booking_cancelled",
    "calendar_checked",
    "calendar_has_conflict",
    "sms_sent",
    "email_sent",
    "to_phone",
    "destination_preview",
    "start_iso",
    "end_iso",
    "suggested_slot_count",
    "message_id",
  ];
  return keys.reduce((result, key) => {
    if (metadata[key] !== undefined && metadata[key] !== null && metadata[key] !== "") {
      result[key] = metadata[key];
    }
    return result;
  }, {});
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
  log("Knowledge base edited", { unsaved: true, chars: (knowledgeBaseInput.value || "").length });
});

systemPromptInput.addEventListener("change", () => {
  log("Prompt edited", { unsaved: true, chars: (systemPromptInput.value || "").length });
});

saveProfileButton.addEventListener("click", () => saveProfile().catch((error) => log("Profile save failed", { error: error.message })));

savePromptButton.addEventListener("click", () => savePrompt().catch((error) => log("Prompt save failed", { error: error.message })));

saveKbButton.addEventListener("click", () => saveKb().catch((error) => log("Knowledge base save failed", { error: error.message })));

resetClientKitButton.addEventListener("click", () => resetClientKit().catch((error) => log("Client kit reset failed", { error: error.message })));

refreshCallNotesButton.addEventListener("click", () => refreshMetrics().catch((error) => log("Call notes refresh failed", { error: error.message })));

evaluateCallButton.addEventListener("click", () => evaluateCurrentCall().catch((error) => {
  evaluationStatusLine.textContent = error.message;
  log("Evaluation load failed", { error: error.message });
}));

saveEvaluationButton.addEventListener("click", () => saveEvaluation().catch((error) => {
  evaluationStatusLine.textContent = error.message;
  log("Evaluation save failed", { error: error.message });
}));

evaluationNotesInput.addEventListener("input", updateEvaluationPreview);
evaluationVersionInput.addEventListener("change", () => {
  evaluationVersionInput.value = sanitizeBotVersion(evaluationVersionInput.value || DEFAULT_EVALUATION_VERSION);
  refreshEvaluationVersionSummary();
});

toolsEnabledInput.addEventListener("change", () => {
  syncToolStateFromInputs();
  log("Tools toggled", { client_id: state.clientId, tools_enabled: state.toolsEnabled });
});

integrationStatusButton.addEventListener("click", () => refreshIntegrationStatus().catch((error) => {
  log("Integration status failed", { error: error.message });
  integrationStatusLine.textContent = error.message;
}));

loadConfig().catch((error) => {
  setStatus("Config failed");
  log("Config failed", { error: error.message });
});
