"""
==============================================================================
PHASE 1: MAIN APPLICATION ENTRY POINT & BASE FLOATING HUD LAUNCHER
==============================================================================
Restores the default launch state:
1. Base HUD: A small, borderless, transparent, always-on-top floating logo window (150x150)
   anchored to the bottom-right corner of the user's primary monitor.
2. Maximized HUD: The modern, dark-tech terminal dashboard (1280x800) is toggled
   via global hotkey F8 or UI controls.
3. Global Hotkeys: Registered via `keyboard` (and pynput fallback):
   - F8: Toggles between Floating Logo and Maximized HUD.
   - Right Alt: Push-to-Talk (Idle) or Instant Speech Interruption (Speaking).
"""

import sys
import os
import time
import ctypes
import threading
import pygame
import webview

import config
from services.state_service import state_machine, AssistantState
from services.audio_service import speak, set_audio_hud_hooks
from services.speech_service import (
    wake_word_listener,
    run_global_hotkeys_listener,
    set_speech_callbacks
)
from services.server_service import (
    run_flask,
    execute_intent,
    set_window_instance,
    toggle_ui_mode
)


def apply_win32_window_styles(window_instance: webview.Window) -> None:
    """Apply Win32 API styles to keep the Base HUD window seamlessly floating on top."""
    time.sleep(1.0)
    try:
        if window_instance:
            user32 = ctypes.windll.user32
            hwnd = None
            if hasattr(window_instance, 'native') and hasattr(window_instance.native, 'Handle'):
                hwnd = window_instance.native.Handle.ToInt32()
            elif hasattr(window_instance, 'hwnd'):
                hwnd = window_instance.hwnd

            if hwnd:
                # HWND_TOPMOST (-1), SWP_NOMOVE (0x0002) | SWP_NOSIZE (0x0001) | SWP_NOACTIVATE (0x0010)
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
    except Exception as e:
        print(f"[Window Style Error]: {e}")


def main() -> None:
    """Bootstrap and start all L.E.O. assistant sub-systems."""
    print("=" * 70)
    print("  L.E.O. CYBERNETIC DESKTOP ORCHESTRATOR // INITIALIZING  ")
    print("  Base State: Floating Logo (150x150) | Hotkeys: [F8 -> Toggle HUD] [Right Alt -> PTT/Interrupt]")
    print(f"  AI Model: {config.GROQ_MODEL} | Vision: {config.GEMINI_MODEL}")
    print("=" * 70)

    # 1. Initialize Pygame Audio Mixer
    pygame.mixer.init()

    # 2. Launch background service daemons (Flask server, wake-word, global hotkeys)
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=wake_word_listener, kwargs={"speak_func": speak}, daemon=True).start()
    threading.Thread(target=run_global_hotkeys_listener, daemon=True).start()

    # ========================================================================
    # PHASE 1.1: RESTORE BASE HUD FLOATING LOGO GEOMETRY (150x150)
    # ========================================================================
    BASE_WINDOW_SIZE = 150
    corner_x, corner_y = 100, 100
    try:
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        corner_x = screen_w - BASE_WINDOW_SIZE - 30
        corner_y = screen_h - BASE_WINDOW_SIZE - 65
    except Exception as e:
        print(f"[Screen Metrics Warning]: {e}")

    # Create the floating base HUD window
    window_instance = webview.create_window(
        title="L.E.O. HUD",
        url=f"http://{config.FLASK_HOST}:{config.FLASK_PORT}/hud",
        width=BASE_WINDOW_SIZE,
        height=BASE_WINDOW_SIZE,
        min_size=(BASE_WINDOW_SIZE, BASE_WINDOW_SIZE),
        x=corner_x,
        y=corner_y,
        resizable=True,
        frameless=True,
        transparent=True,
        on_top=True,
        easy_drag=True,
        background_color='#030712'
    )

    # Connect active window reference and default coordinates to services
    set_window_instance(window_instance, default_coords=(corner_x, corner_y))
    set_audio_hud_hooks(window=window_instance)
    set_speech_callbacks(
        command_callback=execute_intent,
        toggle_ui_callback=toggle_ui_mode,
        window=window_instance
    )

    # State Machine UI broadcast listener
    def on_state_changed(old_state: AssistantState, new_state: AssistantState, reason: str) -> None:
        if window_instance:
            try:
                window_instance.evaluate_js(
                    f"window.setHudState && window.setHudState('{new_state.value}');"
                )
            except Exception:
                pass

    state_machine.subscribe(on_state_changed)

    # Apply Win32 Topmost in background thread
    threading.Thread(target=apply_win32_window_styles, args=(window_instance,), daemon=True).start()

    # Start pywebview main event loop
    try:
        webview.start(gui='edgechromium')
    except Exception:
        webview.start()


if __name__ == '__main__':
    main()
