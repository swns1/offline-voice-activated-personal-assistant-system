"""Decides whether Ash's local-AI features (chat, chained commands,
loose-phrasing understanding, screen description) are on, per the
`ollama.enabled` setting:

- true / false force them on or off.
- "auto" (the default) turns them on only while an Ollama server is
  actually running at `ollama.host` with the configured text model
  downloaded. Installing Ollama and pulling the model is all it takes --
  no config edit -- and a PC without Ollama behaves exactly as if the
  features were switched off (plain "I'm not sure what you mean", never
  "Ollama isn't running").

The check is cached for a short while so it doesn't add a network
round-trip to every command, but still notices Ollama being started or
stopped while Ash is running (e.g. Ash autostarting at login before
Ollama's own tray app has come up). Every call site asks ai_enabled()
instead of reading `config.ollama.enabled` directly, so this is the one
place that decision lives.
"""
import time

from ash.config import Config
from ash.privacy import consent, egress

READY = "ready"
NOT_RUNNING = "not_running"
MODEL_MISSING = "model_missing"

_CACHE_SECONDS = 30.0
# Short on purpose: Ollama is a local server, so a refused connection
# comes back instantly -- this only bounds the odd case of a host that
# silently drops packets.
_TIMEOUT_SECONDS = 1.0

# (host, model) -> (checked_at monotonic seconds, status)
_cache: dict[tuple[str, str], tuple[float, str]] = {}


def ai_enabled(config: Config) -> bool:
    if not egress.is_local_url(config.ollama.host) and consent.offline_mode():
        return False  # an Ollama server on another machine is off this PC
    setting = config.ollama.enabled
    if setting == "auto":
        return server_status(config) == READY
    return bool(setting)


def server_status(config: Config, *, fresh: bool = False) -> str:
    """READY, NOT_RUNNING, or MODEL_MISSING for the configured host/text
    model. `fresh=True` skips the cache (used by on-demand diagnostics)."""
    key = (config.ollama.host, config.ollama.model)
    now = time.monotonic()
    cached = _cache.get(key)
    if not fresh and cached is not None and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    status = _probe(config.ollama.host, config.ollama.model)
    _cache[key] = (now, status)
    return status


def has_model(installed_names: set[str], model: str) -> bool:
    """Ollama lists pulled models with an explicit tag ("llama3.2:latest");
    the config usually names them without one ("llama3.2")."""
    if model in installed_names:
        return True
    return ":" not in model and f"{model}:latest" in installed_names


def _probe(host: str, model: str) -> str:
    try:
        response = egress.get(f"{host}/api/tags", feature=egress.LOCAL_AI.key, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        names = {m.get("name", "") for m in response.json().get("models", [])}
    except Exception:
        return NOT_RUNNING
    return READY if has_model(names, model) else MODEL_MISSING


CHAT_TIMEOUT_SECONDS = 60.0  # CPU inference on a long answer can take a while
# One context size for every request. Ollama loads a model for a given
# context size, so mixing sizes (8192 for tool calls, the 4096 default
# for everything else) reloads the model on each switch: measured at up
# to 47 s. 8192 leaves room for the ~3,700-token tool list.
CONTEXT_TOKENS = 8192


def chat(config: Config, messages: list[dict], *, system: str | None = None, format: str | dict | None = None,
         tools: list[dict] | None = None, options: dict | None = None, model: str | None = None,
         keep_alive: str | None = None, timeout: float = CHAT_TIMEOUT_SECONDS) -> dict:
    """One /api/chat call to the configured model, through the network
    gate (a local server never leaves the PC; one on another machine is
    the "AI server" online feature). Returns the reply message: its
    "content", and "tool_calls" if `tools` were offered. Raises on
    failure (egress.NetworkUnreachable if Ollama isn't running)."""
    payload: dict = {
        "model": model or config.ollama.model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": False,
    }
    if format is not None:
        payload["format"] = format
    if tools:
        payload["tools"] = tools
    payload["options"] = {"num_ctx": CONTEXT_TOKENS, **(options or {})}
    if keep_alive is not None:  # how long the model stays loaded afterwards (Ollama's default: 5 minutes)
        payload["keep_alive"] = keep_alive
    response = egress.post(f"{config.ollama.host}/api/chat", feature=egress.LOCAL_AI.key, json=payload,
                           timeout=timeout)
    response.raise_for_status()
    return response.json().get("message", {}) or {}
