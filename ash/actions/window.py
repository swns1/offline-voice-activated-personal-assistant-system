"""Closes/minimizes apps and windows -- the missing opposite of
open_app.py's launch. Closing a *named* app terminates its process
(psutil); there's no window handle to target without one, so this is a
harder stop than clicking the X -- an accepted trade-off for a voice
command. Closing/minimizing "this"/"the window" instead targets the
current foreground window, via a graceful WM_CLOSE (not a hard kill)
for close, and ShowWindow(SW_MINIMIZE) for minimize.
"""
import logging
import os

import psutil
import win32con
import win32gui

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.matcher import match_app
from ash.registry.schema import Registry


def handle_close_app(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    target = target.strip()
    if not target:
        tts.say("Close what?")
        return HandlerResult()

    process_name = _resolve_process_name(target, registry)
    matches = _find_processes(process_name or target)
    if not matches:
        log.info("No running process matches %r", target)
        tts.say(f"I don't see {target} running.")
        return HandlerResult()

    for proc in matches:
        try:
            proc.terminate()
        except psutil.Error:
            log.exception("Failed to terminate process %s", proc)

    log.info("Closed %d process(es) matching %r", len(matches), target)
    tts.say(f"Closing {target}.")
    return HandlerResult()


def _resolve_process_name(target: str, registry: Registry) -> str | None:
    """If the target matches a registry entry launched as a plain .exe,
    derive its process name from the launch target instead of relying on
    a loose substring match against the target phrase itself."""
    result = match_app(target, registry)
    if result is None or result.entry.launch.get("type") != "exe":
        return None
    exe_path = result.entry.launch.get("target", "")
    basename = os.path.basename(os.path.expandvars(exe_path))
    return basename[:-4] if basename.lower().endswith(".exe") else basename


def _find_processes(name_or_target: str) -> list:
    normalized = name_or_target.lower()
    matches = []
    for proc in psutil.process_iter(["name"]):
        proc_name = (proc.info.get("name") or "").lower()
        if not proc_name:
            continue
        basename = proc_name[:-4] if proc_name.endswith(".exe") else proc_name
        if normalized == basename or normalized in basename or basename in normalized:
            matches.append(proc)
    return matches


def handle_close_window(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        tts.say("I can't tell what window is focused.")
        return HandlerResult()
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    log.info("Sent WM_CLOSE to foreground window %s", hwnd)
    tts.say("Closing.")
    return HandlerResult()


def handle_minimize_window(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        tts.say("I can't tell what window is focused.")
        return HandlerResult()
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    log.info("Minimized foreground window %s", hwnd)
    tts.say("Minimized.")
    return HandlerResult()
