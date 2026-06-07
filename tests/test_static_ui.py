from pathlib import Path


APP_JS = Path("static/app.js")


def test_hume_prepare_refreshes_controls_after_session_creation():
    script = APP_JS.read_text()
    start = script.index('if (state.transport === "hume_evi")')
    end = script.index('const room = await postJson("/api/rooms"')
    hume_prepare_branch = script[start:end]

    assert "startPolling();" in hume_prepare_branch
    assert "renderControls();" in hume_prepare_branch


def test_hume_join_sends_session_settings_before_microphone_streaming():
    script = APP_JS.read_text()
    start = script.index("async function joinHume()")
    end = script.index("async function startHumeRecorder")
    join_hume = script[start:end]

    settings_send = join_hume.index("socket.send(JSON.stringify(state.humeSession.session_settings));")
    recorder_start = join_hume.index("await startHumeRecorder(socket);")

    assert "hume.client.session_settings_sent" in join_hume
    assert settings_send < recorder_start


def test_dashboard_metrics_poll_latest_call_without_local_call_state():
    script = APP_JS.read_text()
    start = script.index("async function refreshMetrics()")
    end = script.index("function renderTranscript")
    refresh_metrics = script[start:end]

    assert '"/api/analytics/summary"' in refresh_metrics
    assert "summary.latest_call_id" in refresh_metrics
    assert "summary.avg_stt_processing_ms ?? summary.avg_speech_to_transcript_ms" in refresh_metrics
    assert "if (!state.callId && metricsCallId)" in refresh_metrics


def test_tools_controls_are_default_and_sent_to_agent_start():
    script = APP_JS.read_text()
    start = script.index("function requestPayload()")
    end = script.index("async function prepare()")
    request_payload = script[start:end]

    assert "toolsEnabled: true" in script
    assert "tools_enabled" in request_payload
    assert "client_id" in request_payload
    assert "caller_phone" in request_payload
    assert "knowledge_base" in request_payload
    assert "callerPhoneInput" in script
    assert "knowledgeBaseInput" in script
    assert "callNotesOutput" in script
    assert "/api/analytics/call-notes" in script
    assert "renderToolTerminalEvents" in script
    assert "Tool succeeded" in script
    assert "tool.call.completed" in script
    assert "state.config?.tools_enabled" in script
    assert "integrationCardsForTools" in script
    assert "/api/client-config" in script
    assert "/api/client-config/reset" in script
    assert "resetClientKitButton" in script
    assert "/api/evaluations/call" in script
    assert "evaluateCallButton" in script
    assert "saveEvaluationButton" in script
    assert '"/api/agent/stop", { call_id: state.callId }' in script
    assert "/api/integrations/nango/connect-session" in script
    assert 'type="checkbox"' in Path("static/index.html").read_text()
    assert "Reset to Current Stack" in Path("static/index.html").read_text()
    assert "Evaluate Current Call" in Path("static/index.html").read_text()
    assert 'value="v0.4"' in Path("static/index.html").read_text()
    assert "dictateEvaluationNotesButton" in script
    assert "startEvaluationDictation" in script
    assert "/api/analytics/tool-evaluation" in script
    assert "renderToolEvaluation" in script
    assert "tool.intent.parsed" in script
    assert "tool.execution.result" in script
    assert "Tool Diagnostics" in Path("static/index.html").read_text()
    assert "refreshToolEvaluationButton" in Path("static/index.html").read_text()
