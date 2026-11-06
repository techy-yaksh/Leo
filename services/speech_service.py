"""
==============================================================================
PHASE 1 & 3: GLOBAL HOTKEYS & INTERRUPTIBLE PUSH-TO-TALK LISTENER
==============================================================================
Implements:
- `keyboard` module global hotkey listeners for F8 and Right Alt.
- F8: Toggles between Base HUD (Floating Logo 150x150) and Maximized/Expanded HUD.
- Right Alt:
  * If State == Speaking: Raises stop_audio=True, halts audio, instantly switches to Listening.
  * If State == Idle: Initiates Push-to-Talk.
- Thread-safe state transitions and offline wake-word monitoring.
"""

import os
import sys
import uuid
import wave
import time
import tempfile
import threading
from typing import Callable, Optional

import numpy as np
import pyaudio
import speech_recognition as sr
import keyboard
from pynput import keyboard as pynput_keyboard
import openwakeword.utils
from openwakeword.model import Model

import config
from services.state_service import state_machine, AssistantState
from services.audio_service import request_stop_audio

# Initialize global speech recognizer
recognizer = sr.Recognizer()
recognizer.energy_threshold = config.SPEECH_ENERGY_THRESHOLD
recognizer.dynamic_energy_threshold = config.SPEECH_DYNAMIC_ENERGY

# PTT Audio State
is_ptt_recording: bool = False
ptt_audio_frames: list[bytes] = []
ptt_stream = None
ptt_pyaudio = pyaudio.PyAudio()

# Intent dispatch callback, UI toggle callback, and window reference
_command_callback: Optional[Callable[[str], str]] = None
_toggle_ui_callback: Optional[Callable[[], bool]] = None
_window_ref = None


def set_speech_callbacks(
    command_callback: Callable[[str], str],
    toggle_ui_callback: Optional[Callable[[], bool]] = None,
    window=None
) -> None:
    """Register callbacks for intent execution, F8 UI geometry toggling, and UI window handle."""
    global _command_callback, _toggle_ui_callback, _window_ref
    _command_callback = command_callback
    _toggle_ui_callback = toggle_ui_callback
    _window_ref = window


# ============================================================================
# PHASE 3: INTERRUPTIBLE PUSH-TO-TALK & SPEECH ENGINE
# ============================================================================
def start_ptt() -> None:
    """Open microphone stream and begin recording audio frames for push-to-talk."""
    global is_ptt_recording, ptt_audio_frames, ptt_stream
    if is_ptt_recording:
        return

    is_ptt_recording = True
    ptt_audio_frames = []

    state_machine.transition_to(AssistantState.LISTENING, "push_to_talk_active")
    if _window_ref:
        try:
            _window_ref.evaluate_js("window.setHudState && window.setHudState('listening');")
        except Exception:
            pass

    try:
        ptt_stream = ptt_pyaudio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )
        print("\n🎙️ MIC OPEN - Listening (Push-to-Talk)...")

        def record_loop() -> None:
            while is_ptt_recording and ptt_stream:
                try:
                    data = ptt_stream.read(1024, exception_on_overflow=False)
                    ptt_audio_frames.append(data)
                except Exception:
                    pass

        threading.Thread(target=record_loop, daemon=True).start()
    except Exception as e:
        print(f"[PTT Error]: Could not open mic: {e}")
        is_ptt_recording = False
        state_machine.transition_to(AssistantState.IDLE, "ptt_mic_open_error")


def stop_ptt() -> None:
    """Close microphone stream, save recorded audio to temp WAV, and transcribe."""
    global is_ptt_recording, ptt_stream, ptt_audio_frames
    if not is_ptt_recording:
        return

    is_ptt_recording = False
    print("🔴 MIC CLOSED - Processing speech...")
    state_machine.transition_to(AssistantState.PROCESSING, "ptt_transcribing")

    if ptt_stream:
        try:
            ptt_stream.stop_stream()
            ptt_stream.close()
        except Exception:
            pass
        ptt_stream = None

    if not ptt_audio_frames:
        state_machine.transition_to(AssistantState.IDLE, "ptt_no_audio_frames")
        return

    # 1. Save raw audio to temporary WAV file
    temp_wav = os.path.join(tempfile.gettempdir(), f"leo_ptt_{uuid.uuid4().hex[:6]}.wav")
    try:
        wf = wave.open(temp_wav, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(ptt_pyaudio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(16000)
        wf.writeframes(b''.join(ptt_audio_frames))
        wf.close()

        # 2. Transcribe asynchronously in background thread to prevent UI lockup
        def process_audio() -> None:
            try:
                with sr.AudioFile(temp_wav) as source:
                    audio_data = recognizer.record(source)
                    command = recognizer.recognize_google(audio_data).lower()
                    print(f"[PTT Recognized]: {command}")
                    if command and _command_callback:
                        _command_callback(command)
                    else:
                        state_machine.transition_to(AssistantState.IDLE, "ptt_empty_command")
            except sr.UnknownValueError:
                print("[PTT] Could not understand audio")
                state_machine.transition_to(AssistantState.IDLE, "ptt_unknown_speech")
            except Exception as e:
                print(f"[PTT Transcribe Error]: {e}")
                state_machine.transition_to(AssistantState.IDLE, "ptt_transcribe_error")
            finally:
                try:
                    if os.path.exists(temp_wav):
                        os.remove(temp_wav)
                except Exception:
                    pass

        threading.Thread(target=process_audio, daemon=True).start()
    except Exception as e:
        print(f"[PTT Save Error]: {e}")
        state_machine.transition_to(AssistantState.IDLE, "ptt_wav_save_error")


# ============================================================================
# PHASE 1 & 3: HOTKEY EVENT HANDLERS (RIGHT ALT & F8)
# ============================================================================
def handle_right_alt_press() -> None:
    """
    PHASE 3.3: Right Alt keypress handler.
    - If State == Speaking: sets stop_audio = True, halts audio, instantly switches to Listening.
    - If State == Idle: initiates standard Push-to-Talk.
    """
    current_state = state_machine.current_state

    if current_state == AssistantState.SPEAKING:
        print("\n[Hotkey] Right Alt pressed during SPEAKING -> INTERRUPTING AUDIO OUTPUT!")
        request_stop_audio()
        state_machine.transition_to(AssistantState.LISTENING, "speech_interrupted_by_user")
        start_ptt()
    elif current_state in (AssistantState.IDLE, AssistantState.LISTENING):
        start_ptt()


def handle_right_alt_release() -> None:
    """Right Alt release handler: concludes audio recording."""
    global is_ptt_recording
    if is_ptt_recording:
        stop_ptt()


def handle_f8_press() -> None:
    """
    PHASE 1.3: F8 keypress handler.
    Toggles the UI geometry and visibility between Floating Logo (150x150)
    and Maximized/Expanded HUD.
    """
    print("\n[Hotkey] F8 pressed -> Toggling UI between Floating Logo and Maximized HUD.")
    if _toggle_ui_callback:
        _toggle_ui_callback()


def run_global_hotkeys_listener() -> None:
    """
    Register and run global low-level hooks for F8 and Right Alt using the `keyboard` module,
    with pynput as a resilient secondary fallback hook.
    """
    time.sleep(1.0)
    print("[Global Hotkeys] Initializing 'keyboard' module listeners for F8 and Right Alt...")

    try:
        # Register F8 for UI toggle
        keyboard.add_hotkey('f8', handle_f8_press)

        # Register Right Alt press and release
        keyboard.on_press_key('right alt', lambda _: handle_right_alt_press())
        keyboard.on_release_key('right alt', lambda _: handle_right_alt_release())

        print("[Global Hotkeys] 'keyboard' listeners active: [F8 -> Toggle HUD] | [Right Alt -> PTT/Interrupt].")
    except Exception as e:
        print(f"[Keyboard Module Hook Error]: {e}. Activating pynput hook fallback...")

        # Resilient fallback with pynput
        def pynput_on_press(key):
            if key == pynput_keyboard.Key.f8:
                handle_f8_press()
            elif key == pynput_keyboard.Key.alt_r:
                handle_right_alt_press()

        def pynput_on_release(key):
            if key == pynput_keyboard.Key.alt_r:
                handle_right_alt_release()

        listener = pynput_keyboard.Listener(on_press=pynput_on_press, on_release=pynput_on_release)
        listener.daemon = True
        listener.start()


def wake_word_listener(speak_func: Optional[Callable[..., None]] = None) -> None:
    """Continuously monitor microphone for the wake word using openWakeWord."""
    global _command_callback, _window_ref
    try:
        openwakeword.utils.download_models()
        model_name = config.DEFAULT_WAKE_WORD_MODEL
        oww_model = Model(wakeword_models=[model_name], inference_framework="onnx")

        format_type, channels, rate, chunk = pyaudio.paInt16, 1, 16000, 1280
        audio = pyaudio.PyAudio()
        stream = audio.open(format=format_type, channels=channels, rate=rate, input=True, frames_per_buffer=chunk)

        print(f"\n[L.E.O.] Wake-word listener active (Listening for: '{model_name}')...")
        spinner, frame_count = ['|', '/', '-', '\\'], 0

        while True:
            data = stream.read(chunk, exception_on_overflow=False)
            audio_frame = np.frombuffer(data, dtype=np.int16)

            frame_count += 1
            if frame_count % 5 == 0:
                symbol = spinner[(frame_count // 5) % len(spinner)]
                sys.stdout.write(f"\r[Listening {symbol}] Mic active...")
                sys.stdout.flush()

            prediction = oww_model.predict(audio_frame)
            for _, score in prediction.items():
                if score > config.WAKE_WORD_CONFIDENCE_THRESHOLD:
                    sys.stdout.write(f"\n\n[Triggered] Wake word detected!\n")
                    sys.stdout.flush()

                    state_machine.transition_to(AssistantState.LISTENING, "wake_word_detected")
                    if _window_ref:
                        try:
                            _window_ref.show()
                            _window_ref.restore()
                        except Exception:
                            pass

                    stream.stop_stream()
                    if speak_func:
                        try:
                            speak_func("Online.", non_blocking=False)
                        except TypeError:
                            speak_func("Online.")

                    consecutive_silence_count = 0
                    while True:
                        state_machine.transition_to(AssistantState.LISTENING, "awaiting_speech_phrase")
                        with sr.Microphone() as source:
                            recognizer.adjust_for_ambient_noise(source, duration=0.3)
                            try:
                                recorded_audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                                command = recognizer.recognize_google(recorded_audio).lower()
                            except Exception:
                                command = ""

                        if command:
                            consecutive_silence_count = 0
                            clean_cmd = command.lower().strip()
                            if any(term in clean_cmd for term in ["sleep", "go to sleep", "nevermind", "that's all", "bye"]):
                                if _command_callback:
                                    _command_callback(command)
                                break
                            if _command_callback:
                                state_machine.transition_to(AssistantState.PROCESSING, "voice_command_dispatched")
                                _command_callback(command)
                        else:
                            consecutive_silence_count += 1
                            if consecutive_silence_count >= 3:
                                if speak_func:
                                    try:
                                        speak_func("Going to standby.", non_blocking=False)
                                    except TypeError:
                                        speak_func("Going to standby.")
                                state_machine.transition_to(AssistantState.IDLE, "voice_timeout_standby")
                                break

                    oww_model.reset()
                    state_machine.transition_to(AssistantState.IDLE, "resuming_wake_word_stream")
                    stream.start_stream()
    except Exception as e:
        print(f"\n[Wake-word Error]: {e}")
        state_machine.transition_to(AssistantState.IDLE, "wake_word_exception")
