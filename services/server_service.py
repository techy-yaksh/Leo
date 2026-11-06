"""
==============================================================================
SERVER ROUTING, UI GEOMETRY TOGGLE, AND INTENT DISPATCHER
==============================================================================
Provides Flask REST and SSE endpoints, coordinates the UI geometry toggle between
the Base Floating Logo (150x150) and the Maximized/Expanded HUD, and manages intent execution.
"""

import os
import sys
import json
import uuid
import time
import string
import asyncio
import tempfile
import threading
import logging
from typing import Any, Generator, Optional

from flask import Flask, render_template, request, jsonify, Response
import edge_tts
import pygame
import psutil

import config
from services.state_service import state_machine, AssistantState
from services.agent_service import process_agent_command, process_agent_command_stream
from services.audio_service import speak
from services.vision_service import capture_screen_b64, analyze_screen_with_gemini

# Suppress Werkzeug HTTP request logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Initialize Flask application pointing to project base directory
app = Flask(__name__, template_folder=str(config.BASE_DIR))

# Window handle and UI expansion state
window_instance: Any = None
is_expanded: bool = False
last_toggle_time: float = 0.0
corner_coords: tuple[int, int] = (0, 0)


def set_window_instance(window: Any, default_coords: tuple[int, int] = (0, 0)) -> None:
    """Register the pywebview window instance and baseline screen coordinates."""
    global window_instance, corner_coords
    window_instance = window
    corner_coords = default_coords


# ============================================================================
# PHASE 1.1 & 1.2: UI GEOMETRY TOGGLE (FLOATING LOGO <-> MAXIMIZED HUD)
# ============================================================================
def toggle_ui_mode(force_state: Optional[bool] = None) -> bool:
    """
    Toggles the window geometry and visibility between:
    - Base State: Small borderless floating HUD (150x150) in the corner.
    - Maximized HUD: Expanded dark-tech terminal dashboard (1280x800).
    Called via global hotkey F8 or frontend button.
    """
    global window_instance, is_expanded, last_toggle_time, corner_coords
    now = time.time()
    if now - last_toggle_time < 0.25:
        return is_expanded
    last_toggle_time = now

    if force_state is not None:
        is_expanded = force_state
    else:
        is_expanded = not is_expanded

    if window_instance:
        try:
            time.sleep(0.05)
            if is_expanded:
                print("[UI Geometry] Expanding to Maximized HUD Terminal (1280x800)...")
                # Expand window to full dashboard
                window_instance.resize(1280, 800)
                # Notify frontend JS to display the terminal panel
                window_instance.evaluate_js("window.onBackendToggleExpand && window.onBackendToggleExpand(true);")
            else:
                print("[UI Geometry] Collapsing to Base Floating Logo (150x150)...")
                # Collapse window back to mini 150x150 corner widget
                window_instance.resize(150, 150)
                # Notify frontend JS to display the floating logo view
                window_instance.evaluate_js("window.onBackendToggleExpand && window.onBackendToggleExpand(false);")
        except Exception as e:
            print(f"[UI Resize Error]: {e}")

    return is_expanded


def execute_intent(user_text: str) -> str:
    """Core intent dispatcher: routes commands to agent reasoning, audio speech, or local lifecycle actions."""
    global window_instance
    if not user_text:
        state_machine.transition_to(AssistantState.IDLE, "empty_command")
        return ""

    clean_text = user_text.translate(str.maketrans('', '', string.punctuation)).lower().strip()
    print(f"\n[Command Received]: {clean_text}")

    state_machine.update_dialogue(user_text=user_text, leo_text="Analyzing...")
    state_machine.transition_to(AssistantState.PROCESSING, "intent_dispatched")

    # Standby command handling
    if "sleep" in clean_text or "go to sleep" in clean_text:
        response_text = "Entering standby mode."
        state_machine.update_dialogue(leo_text=response_text)
        speak(response_text, non_blocking=True)
        return response_text

    # Immediate shutdown command handling
    if any(k in clean_text for k in ["exit", "quit", "power down"]):
        response_text = "Powering down system. Goodbye."
        state_machine.update_dialogue(leo_text=response_text)

        def _fast_goodbye() -> None:
            try:
                unique_file = os.path.join(tempfile.gettempdir(), f"leo_bye_{uuid.uuid4().hex[:6]}.mp3")
                asyncio.run(
                    edge_tts.Communicate("Powering down system. Goodbye.", config.TTS_VOICE, rate=config.TTS_RATE).save(unique_file)
                )
                pygame.mixer.music.load(unique_file)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(15)

                pygame.mixer.music.unload()
            except Exception:
                pass
            finally:
                if window_instance:
                    try:
                        window_instance.destroy()
                    except Exception:
                        pass
                time.sleep(0.5)
                os._exit(0)

        threading.Thread(target=_fast_goodbye, daemon=True).start()
        return response_text

    # PHASE 4: Direct Screen Vision Trigger
    vision_triggers = ["what is on my screen", "analyze screen", "look at screen", "read screen", "look at this"]
    if any(k in clean_text for k in vision_triggers):
        state_machine.update_dialogue(leo_text="Capturing display via MSS and analyzing with Gemini 3.8 Flash...")
        b64_img = capture_screen_b64()
        response_text = analyze_screen_with_gemini(user_text, b64_img=b64_img)
        state_machine.update_dialogue(leo_text=response_text)
        speak(response_text, non_blocking=True)
        return response_text

    # Execute intelligent command via Groq Agent
    print(f"[Orchestrator] Dispatching to Groq Agent: \"{user_text}\"")
    response_text = process_agent_command(user_text)
    print(f"[Orchestrator] Agent generated response ({len(response_text)} chars): \"{response_text[:80]}...\"")
    
    state_machine.update_dialogue(leo_text=response_text)
    print("[Orchestrator] Routing response to Speech/Audio engine...")
    speak(response_text, non_blocking=True)

    return response_text


# ==============================================================================
# FLASK ROUTE DEFINITIONS
# ==============================================================================

@app.route('/process_command', methods=['POST'])
def process_command():
    """Endpoint for user text commands sent from the terminal interface."""
    data = request.json or {}
    user_text = data.get('command', '').strip()
    return jsonify({"response": execute_intent(user_text)})


@app.route('/stream_command', methods=['POST'])
def stream_command():
    """Server-Sent Events (SSE) streaming endpoint for instantaneous, token-by-token replies."""
    data = request.json or {}
    user_text = data.get('command', '').strip()

    if not user_text:
        return jsonify({"error": "No command provided"}), 400

    clean_text = user_text.translate(str.maketrans('', '', string.punctuation)).lower().strip()

    # Intercept exit or sleep commands without streaming
    if any(k in clean_text for k in ["exit", "quit", "power down", "sleep", "go to sleep"]):
        resp = execute_intent(user_text)
        def single_event():
            yield f"data: {json.dumps({'type': 'final', 'data': resp})}\n\n"
        return Response(single_event(), mimetype='text/event-stream')

    def generate_events() -> Generator[str, None, None]:
        state_machine.transition_to(AssistantState.PROCESSING, "sse_stream_started")
        state_machine.update_dialogue(user_text=user_text, leo_text="")

        full_response_parts: list[str] = []
        for event in process_agent_command_stream(user_text):
            if event["type"] == "token":
                full_response_parts.append(event["data"])
                current_accumulated = "".join(full_response_parts)
                state_machine.update_dialogue(leo_text=current_accumulated)

            yield f"data: {json.dumps(event)}\n\n"

        complete_response = "".join(full_response_parts)
        if complete_response:
            speak(complete_response, non_blocking=True)

    return Response(generate_events(), mimetype='text/event-stream')


@app.route('/trigger_vision', methods=['POST'])
def trigger_vision():
    """Dedicated endpoint to trigger multimodal screen analysis immediately."""
    data = request.json or {}
    custom_prompt = data.get('prompt') or "Analyze what is visible on my screen in detail."

    state_machine.update_dialogue(user_text=custom_prompt, leo_text="Scanning screen with Gemini 3.8 Flash...")
    state_machine.transition_to(AssistantState.PROCESSING, "vision_triggered")

    def run_vision_task() -> None:
        b64_img = capture_screen_b64()
        analysis = analyze_screen_with_gemini(custom_prompt, b64_img=b64_img)
        state_machine.update_dialogue(leo_text=analysis)
        speak(analysis, non_blocking=True)

    threading.Thread(target=run_vision_task, daemon=True).start()
    return jsonify({"status": "processing", "message": "Vision capture initiated"})


@app.route('/get_hud_status', methods=['GET'])
def get_hud_status():
    """Poll endpoint used by frontend to sync animation state and dialogue."""
    return jsonify(state_machine.get_snapshot())


@app.route('/get_telemetry', methods=['GET'])
def get_telemetry():
    """Returns live hardware metrics for the modernized cyberpunk HUD gauges."""
    try:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()
        bat_percent = battery.percent if battery else 100
        bat_plugged = battery.power_plugged if battery else True

        snapshot = state_machine.get_snapshot()
        return jsonify({
            "cpu": cpu,
            "ram": ram,
            "battery": bat_percent,
            "plugged": bat_plugged,
            "state": snapshot.get("state", "standby"),
            "groq_model": config.GROQ_MODEL,
            "gemini_model": config.GEMINI_MODEL,
            "is_expanded": is_expanded
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/resize_hud', methods=['POST'])
def resize_hud():
    """Endpoint to trigger window minimization or expansion via hotkey or UI button."""
    data = request.json or {}
    req_expanded = data.get('expanded', not is_expanded)
    res_state = toggle_ui_mode(force_state=req_expanded)
    return jsonify({"status": "ok", "expanded": res_state})


@app.route('/')
@app.route('/crest')
@app.route('/hud')
def index():
    """Render the main HUD HTML dashboard."""
    return render_template(config.FRONTEND_TEMPLATE)


def run_flask() -> None:
    """Run Flask HTTP server in a dedicated thread."""
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.DEBUG_MODE,
        use_reloader=False
    )
