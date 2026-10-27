"""LLM endpoint resolution + failover for the AI bizcollector.

The bot talks to ONE OpenAI-compatible endpoint (Minda) by default. To get
credential-pool failover WITHOUT adding new vendor keys, an optional
CLIProxyAPI sidecar can be configured: it wraps the team's *existing* Claude
Code / ChatGPT / Gemini CLI subscriptions into one OpenAI-compatible API on a
local port (default :8317). When it is set, Minda is tried first and the proxy
is the fallback, so a flaky Minda call no longer drops the AI layer (fail-open
to the deterministic engine still holds if every endpoint is down).

Env (all optional):
  MINDA_BASE_URL / MINDA_API_KEY / MINDA_MODEL   (primary; already used)
  LLM_PROXY_BASE_URL / LLM_PROXY_API_KEY / LLM_PROXY_MODEL   (CLIProxyAPI sidecar)
  LLM_CHAIN_TIMEOUT   per-endpoint timeout override (seconds, default 45)

The API key never appears in logs or messages. Stdlib only.
"""
import os
from urllib.request import Request, urlopen


def _settings_from(prefix, default_model):
    base = os.getenv(prefix + "_BASE_URL")
    key = os.getenv(prefix + "_API_KEY")
    model = os.getenv(prefix + "_MODEL") or default_model
    if not base or not key:
        return None
    return {"name": prefix.lower(), "base_url": base.rstrip("/"),
            "api_key": key, "model": model}


def chain():
    """Ordered list of endpoint tuples (base_url, api_key, model). Minda first
    (if configured), then the CLIProxyAPI sidecar (if configured). Empty list =
    AI layer fully off."""
    out = []
    minda = _settings_from("MINDA", "llm_model_fp8")
    proxy = _settings_from("LLM_PROXY", "gpt-4o-mini")
    if minda:
        out.append((minda["base_url"], minda["api_key"], minda["model"]))
    if proxy:
        out.append((proxy["base_url"], proxy["api_key"], proxy["model"]))
    return out


def first(settings=None):
    """Return the primary endpoint as the (base_url, api_key, model) tuple that
    ai_bizcollector expects, or None. Mirrors ai_bizcollector._minda_settings
    for the single-endpoint case."""
    c = chain() if settings is None else settings
    if not c:
        return None
    return c[0]


def timeout_seconds():
    try:
        return int(os.getenv("LLM_CHAIN_TIMEOUT", "45"))
    except ValueError:
        return 45


def health(endpoint, timeout=8):
    """Cheap liveness probe: does the endpoint answer a 1-token completion?
    endpoint is a (base_url, api_key, model) tuple. Returns True/False; never
    raises."""
    try:
        import json
        req = Request(endpoint[0] + "/chat/completions",
                      data=json.dumps({"model": endpoint[2], "max_tokens": 1,
                                       "messages": [{"role": "user", "content": "hi"}]}).encode(),
                      method="POST",
                      headers={"Authorization": "Bearer " + endpoint[1],
                               "Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def describe():
    """Human-readable status of the chain (keys redacted). For /ai menu / logs."""
    c = chain()
    if not c:
        return "AI endpoints: none configured (deterministic engine only)."
    lines = ["AI endpoints (in failover order):"]
    for i, e in enumerate(c):
        mark = "primary" if i == 0 else "fallback"
        lines.append("  %d. [%s] %s (model %s)" % (i + 1, mark, e[0], e[2]))
    return "\n".join(lines)


DOCKER_COMPOSE = """\
# Optional CLIProxyAPI sidecar (wraps existing Claude/ChatGPT/Gemini CLI logins
# into an OpenAI-compatible API). Run it, log in once with the provider CLI,
# then set LLM_PROXY_BASE_URL / LLM_PROXY_API_KEY in the bot env. No new vendor
# keys needed — it reuses subscriptions you already have.
services:
  cliproxyapi:
    image: eceasy/cli-proxy-api:latest
    restart: unless-stopped
    ports:
      - "8317:8317"
    volumes:
      - ./cliproxy-auths:/app/auths
    command: ["--config", "/app/config.yaml"]
# Bot env afterwards:
#   LLM_PROXY_BASE_URL=http://<host>:8317/v1
#   LLM_PROXY_API_KEY=<any>   (CLIProxyAPI accepts a local token)
#   LLM_PROXY_MODEL=<a model name the sidecar serves>
"""
