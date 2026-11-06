"""
==============================================================================
PHASE 3: INTERRUPTIBLE AUDIO SYSTEM & THREAD-SAFE TTS
==============================================================================
Provides a non-blocking, interruptible Text-to-Speech pipeline.
Implements the global `stop_audio = False` interruption flag checked throughout
the playback loop. If Right Alt is pressed while speaking, the playback aborts
immediately and returns the state machine to Listening.
"""

import os
import re
import sys
import uuid
import queue
import asyncio
import tempfile
import threading
import time
from typing import Callable, Optional

import edge_tts
import pygame

import config
from services.state_service import state_machine, AssistantState

# Fallback offline TTS engine import
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

_window_instance = None
_playback_lock = threading.Lock()

# ============================================================================
# PHASE 3.2: GLOBAL INTERRUPT BOOLEAN FLAG
# ============================================================================
stop_audio: bool = False


def request_stop_audio() -> None:
    """
    PHASE 3.3: Set stop_audio = True and immediately halt active sound card output.
    Called when the user presses 'Right Alt' while State == Speaking.
    """
    global stop_audio
    print("\n[TTS Pipeline] >>> request_stop_audio() CALLED: Interruption flag raised. <<<")
    stop_audio = True
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
    except Exception as e:
        print(f"[Stop Audio Error]: {e}")


def reset_stop_audio() -> None:
    """Reset the interrupt flag for subsequent playback runs."""
    global stop_audio
    stop_audio = False


def set_audio_hud_hooks(window=None) -> None:
    """Register window handle for direct JS state updates."""
    global _window_instance
    _window_instance = window


def ensure_audio_driver() -> bool:
    """Ensure Pygame audio mixer is active and ready for playback."""
    try:
        if not pygame.mixer.get_init():
            print("[Audio Driver] Initializing Pygame mixer (44100Hz, 16-bit, stereo)...")
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            print("[Audio Driver] Mixer successfully initialized.")
        return True
    except Exception as e:
        print(f"[Audio Driver Error] Failed to initialize sound card driver: {e}")
        return False


def clean_tts_text(text: str) -> str:
    """Clean markdown markers, code symbols, and URLs for natural pronunciation."""
    if not text:
        return ""
    text = re.sub(r'[*_~`#>]', '', text)
    text = re.sub(r'https?://\S+', 'link', text)
    return re.sub(r'\s+', ' ', text).strip()


def _speak_offline_fallback(clean_text: str) -> None:
    """Offline fallback using Windows SAPI / pyttsx3."""
    global stop_audio
    if stop_audio:
        return

    print("[TTS Fallback] Executing offline local speech synthesis via pyttsx3/SAPI...")
    if not HAS_PYTTSX3:
        print("[TTS Fallback Error] pyttsx3 is not installed. Unable to speak offline.")
        return

    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 185)
        voices = engine.getProperty('voices')
        if voices:
            engine.setProperty('voice', voices[0].id)
        engine.say(clean_text)
        engine.runAndWait()
        print("[TTS Fallback] Offline speech playback completed.")
    except Exception as ex:
        print(f"[TTS Fallback Critical Error] Failed to speak with pyttsx3: {ex}")


def _execute_speech_worker(clean_text: str, voice: str) -> None:
    """
    PHASE 3.1: Internal synchronous speech execution routine run strictly
    inside its own dedicated background thread to prevent GUI freezing.
    Continually inspects `stop_audio` to enable instant interruption.
    """
    global _window_instance, stop_audio

    # Reset interrupt flag before starting new speech turn
    reset_stop_audio()

    with _playback_lock:
        print(f"\n[TTS Pipeline] Processing speech ({len(clean_text)} chars): \"{clean_text[:60]}...\"")

        # PHASE 2: State Machine transition to SPEAKING
        state_machine.transition_to(AssistantState.SPEAKING, "audio_playback_started")
        if _window_instance:
            try:
                _window_instance.evaluate_js("window.setHudState && window.setHudState('speaking');")
            except Exception:
                pass

        # Split into sentence chunks for instant zero-lag start
        raw_chunks = re.split(r'(?<=[.!?])\s+', clean_text)
        phrases = [c.strip() for c in raw_chunks if len(c.strip()) > 0]
        if not phrases:
            phrases = [clean_text]

        print(f"[TTS Pipeline] Split text into {len(phrases)} sentence chunk(s).")

        # Ensure audio hardware is online
        if not ensure_audio_driver():
            print("[TTS Warning] Pygame mixer unavailable. Falling back to pyttsx3.")
            _speak_offline_fallback(clean_text)
            _reset_hud_state()
            return

        audio_queue: queue.Queue[Optional[str]] = queue.Queue()

        def _play_audio_file(file_path: str) -> bool:
            """
            Plays a single audio file chunk.
            Checks `stop_audio` in tight 10ms intervals for instantaneous user interruption.
            Returns True if completed naturally, False if interrupted.
            """
            global stop_audio
            if not os.path.exists(file_path):
                return False

            if stop_audio:
                print("[TTS Interrupted] stop_audio=True detected before loading audio. Aborting.")
                return False

            try:
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()

                # PHASE 3.3: Interrupt check loop
                while pygame.mixer.music.get_busy():
                    if stop_audio:
                        print("[TTS Interrupted] stop_audio=True detected while playing! Halting audio.")
                        pygame.mixer.music.stop()
                        pygame.mixer.music.unload()
                        return False
                    pygame.time.Clock().tick(30)

                pygame.mixer.music.unload()
                return True
            except Exception as e:
                print(f"[Audio Playback Error] {e}")
                return False
            finally:
                for _ in range(5):
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        break
                    except PermissionError:
                        time.sleep(0.04)
                    except Exception:
                        break

        # Check interrupt flag before generating chunk 1
        if stop_audio:
            _reset_hud_state()
            return

        # 1. Synthesize first sentence chunk immediately
        first_file = os.path.join(tempfile.gettempdir(), f"leo_p0_{uuid.uuid4().hex[:6]}.mp3")
        first_chunk_success = False

        try:
            print(f"[TTS Engine] Generating chunk 1 via Edge-TTS (voice: {voice})...")
            asyncio.run(edge_tts.Communicate(phrases[0], voice, rate=config.TTS_RATE).save(first_file))
            first_chunk_success = True
            print("[TTS Engine] Chunk 1 synthesized successfully.")
        except Exception as e:
            print(f"[TTS Cloud Error] Edge-TTS chunk 1 generation failed: {e}")
            if not stop_audio:
                _speak_offline_fallback(clean_text)
            _reset_hud_state()
            return

        # Check interrupt flag before remaining generations
        if stop_audio:
            _reset_hud_state()
            return

        # 2. Multi-sentence background generator
        if len(phrases) > 1 and first_chunk_success:
            def _gen_remaining() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for idx, phrase in enumerate(phrases[1:], start=1):
                    if stop_audio:
                        print(f"[TTS Gen Cancelled] stop_audio=True detected on phrase {idx}. Halting worker.")
                        break
                    next_file = os.path.join(tempfile.gettempdir(), f"leo_p{idx}_{uuid.uuid4().hex[:6]}.mp3")
                    try:
                        loop.run_until_complete(
                            edge_tts.Communicate(phrase, voice, rate=config.TTS_RATE).save(next_file)
                        )
                        audio_queue.put(next_file)
                    except Exception as ex:
                        print(f"[TTS Chunk {idx} Error]: {ex}")
                audio_queue.put(None)
                loop.close()

            threading.Thread(target=_gen_remaining, daemon=True).start()

        # 3. Play first chunk right away
        time.sleep(0.05)
        completed = _play_audio_file(first_file)
        if not completed or stop_audio:
            print("[TTS Pipeline] First chunk interrupted. Exiting.")
            _reset_hud_state()
            return

        # 4. Stream any remaining queued chunks seamlessly
        if len(phrases) > 1 and first_chunk_success:
            while True:
                if stop_audio:
                    print("[TTS Pipeline] Interruption flag active during queue streaming. Breaking.")
                    break
                next_file = audio_queue.get()
                if next_file is None:
                    break
                time.sleep(0.04)
                if not _play_audio_file(next_file) or stop_audio:
                    break

        print("[TTS Pipeline] Speech playback completed / terminated.")
        _reset_hud_state()


def _reset_hud_state() -> None:
    """Reset HUD state back to IDLE / Standby if not actively listening."""
    global _window_instance
    # Only reset to IDLE if the state wasn't switched to LISTENING during interruption
    if state_machine.current_state == AssistantState.SPEAKING:
        state_machine.transition_to(AssistantState.IDLE, "audio_playback_finished")
        if _window_instance:
            try:
                _window_instance.evaluate_js("window.setHudState && window.setHudState('standby');")
            except Exception:
                pass


def speak(text: str, non_blocking: bool = True, voice: Optional[str] = None) -> None:
    """
    PHASE 3.1: Main TTS entry point.
    Runs strictly in a background thread by default so the caller/UI NEVER freezes.
    """
    target_voice = voice or config.TTS_VOICE
    clean_text = clean_tts_text(text).replace('\n', ' ')

    if not clean_text:
        return

    if non_blocking:
        worker_thread = threading.Thread(
            target=_execute_speech_worker,
            args=(clean_text, target_voice),
            daemon=True
        )
        worker_thread.start()
    else:
        _execute_speech_worker(clean_text, target_voice)
