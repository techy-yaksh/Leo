"""
Strict, thread-safe State Machine for L.E.O. Assistant.
Manages global lifecycle states: IDLE, LISTENING, PROCESSING, SPEAKING.
Prevents state desynchronization, drops, and UI flickering.
"""

import time
import threading
from enum import Enum
from typing import Callable, Any


class AssistantState(str, Enum):
    """Enumeration of assistant runtime states."""
    IDLE = "standby"
    LISTENING = "listening"
    PROCESSING = "thinking"
    SPEAKING = "speaking"


class StateManager:
    """Thread-safe State Machine with listener notifications and diagnostic tracking."""

    def __init__(self, initial_state: AssistantState = AssistantState.IDLE) -> None:
        self._state: AssistantState = initial_state
        self._lock = threading.RLock()
        self._listeners: list[Callable[[AssistantState, AssistantState, str], None]] = []
        self._last_state_change: float = time.time()
        self._last_reason: str = "init"
        self._dialogue_state: dict[str, str] = {
            "user_text": "System online. Standing by...",
            "leo_text": "L.E.O. Neural Core ready. Awaiting instructions.",
            "state": self._state.value
        }

    @property
    def current_state(self) -> AssistantState:
        with self._lock:
            return self._state

    @property
    def value(self) -> str:
        with self._lock:
            return self._state.value

    def transition_to(self, new_state: AssistantState | str, reason: str = "") -> bool:
        """
        Atomically transition to a new state and dispatch notifications to all registered observers.
        """
        if isinstance(new_state, str):
            try:
                new_state = AssistantState(new_state.lower().strip())
            except ValueError:
                # Map common aliases
                if new_state.lower().strip() in ("idle", "standby"):
                    new_state = AssistantState.IDLE
                elif new_state.lower().strip() in ("listening", "listen"):
                    new_state = AssistantState.LISTENING
                elif new_state.lower().strip() in ("processing", "thinking"):
                    new_state = AssistantState.PROCESSING
                elif new_state.lower().strip() in ("speaking", "speak"):
                    new_state = AssistantState.SPEAKING
                else:
                    new_state = AssistantState.IDLE

        with self._lock:
            old_state = self._state
            if old_state == new_state and reason == self._last_reason:
                return False

            self._state = new_state
            self._last_state_change = time.time()
            self._last_reason = reason
            self._dialogue_state["state"] = new_state.value

            print(f"[State Machine] Transition: {old_state.name} -> {new_state.name} ({reason})")

            # Notify observers safely outside lock contention
            listeners_snapshot = list(self._listeners)

        for listener in listeners_snapshot:
            try:
                listener(old_state, new_state, reason)
            except Exception as e:
                print(f"[State Machine Observer Error]: {e}")

        return True

    def subscribe(self, callback: Callable[[AssistantState, AssistantState, str], None]) -> None:
        """Register a callback for state transition events."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def update_dialogue(self, user_text: str | None = None, leo_text: str | None = None) -> None:
        """Thread-safe update of current conversational dialogue."""
        with self._lock:
            if user_text is not None:
                self._dialogue_state["user_text"] = user_text
            if leo_text is not None:
                self._dialogue_state["leo_text"] = leo_text

    def get_snapshot(self) -> dict[str, str]:
        """Return a copy of the current status dictionary for UI polling/SSE."""
        with self._lock:
            return dict(self._dialogue_state)


# Global singleton instance
state_machine = StateManager()
