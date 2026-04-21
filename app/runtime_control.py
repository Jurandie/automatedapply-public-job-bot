from __future__ import annotations

import threading
import time


class RunInterrupted(RuntimeError):
    """Raised when the user requests a safe stop."""


_stop_event = threading.Event()
_pause_event = threading.Event()


def reset_run_control() -> None:
    _stop_event.clear()
    _pause_event.clear()


def request_stop() -> None:
    _stop_event.set()
    _pause_event.clear()


def request_pause() -> None:
    _pause_event.set()


def resume_run() -> None:
    _pause_event.clear()


def is_stop_requested() -> bool:
    return _stop_event.is_set()


def is_paused() -> bool:
    return _pause_event.is_set()


def checkpoint() -> None:
    if _stop_event.is_set():
        raise RunInterrupted("Operacao interrompida pelo usuario.")

    while _pause_event.is_set():
        if _stop_event.is_set():
            raise RunInterrupted("Operacao interrompida pelo usuario.")
        time.sleep(0.2)
