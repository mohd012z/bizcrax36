"""AI bizcollector — Minda-powered intent parsing + AI synthesis for research.

Same method as msasoup's AI_msa: one OpenAI-compatible chat call, strict JSON
reply, fail-open. When Minda is unavailable the deterministic V2 engine still
answers; the AI layer only adds intent parsing and a synthesis paragraph.

Env: MINDA_BASE_URL, MINDA_API_KEY, MINDA_MODEL (default llm_model_fp8).
The API key never appears in logs or messages.
"""
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BANDS = ("all", "micro", "small", "medium", "large")

INTENT_PROMPT = (
    "You are the intent parser of a business-research assistant. "
    "Classify the USER message into ONE intent:\n"
    "research - user wants to find/research high-potential business opportunities\n"
    "search - user wants a keyword search of saved records\n"
    "report - user wants a full report/proposal for a specific business\n"
    "home - user wants the main menu / to start over\n"
    "help - user asks how the assistant works\n"
    "chat - anything else (greeting, small talk)\n"
    "For research/report extract the BUSINESS TOPIC (drop filler like 'find', "
    "'research', 'high potential business'). Also extract the capital band if "
    "mentioned: 'low capital / under rm10k / micro' -> micro; 'small / rm10k-250k' -> "
    "small; 'medium / rm250k-2m' -> medium; 'large / rm2m+' -> large; otherwise all.\n"
    'Reply ONLY JSON: {"intent":"...","topic":"..." or null,"capital":"all"}\n'
    "USER: "
)

SYSTEM_SYNTH = (
    "You are BizCrax AI, a business research analyst. You synthesize ONLY the "
    "evidence provided. Rules: (1) never invent numbers, sources or facts that "
    "are not in the evidence; (2) mark every claim: [FACT] present in evidence, "
    "[INFER] reasonable inference, [ASSUME] assumption; (3) end with the single "
    "most important verification step; (4) max 120 words; plain text."
)


def _minda_settings(base_url=None, api_key=None, model=None):
    base_url = base_url if base_url is not None else os.getenv("MINDA_BASE_URL")
    api_key = api_key if api_key is not None else os.getenv("MINDA_API_KEY")
    model = model if model is not None else os.getenv("MINDA_MODEL", "llm_model_fp8")
    if not base_url or not api_key:
        return None
    return base_url.rstrip("/"), api_key, model


def _endpoints(base_url=None, api_key=None, model=None):
    """Ordered endpoint list for a call. Explicit args -> that single endpoint
    (used by tests). Otherwise the failover chain: Minda, then the optional
    CLIProxyAPI sidecar."""
    if base_url is not None or api_key is not None or model is not None:
        s = _minda_settings(base_url, api_key, model)
        return [s] if s else []
    from backend import llm_endpoints
    return llm_endpoints.chain()


def _chat(settings, messages, max_tokens=300, timeout=45):
    url = settings[0] + "/chat/completions"
    payload = {"model": settings[2], "max_tokens": max_tokens,
               "chat_template_kwargs": {"enable_thinking": False},
               "messages": messages}
    req = Request(url, data=json.dumps(payload).encode(), method="POST",
                  headers={"Authorization": "Bearer " + settings[1],
                           "Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read(1_000_000))
    return data["choices"][0]["message"]["content"].strip()


def _chat_failover(settings, messages, max_tokens=300, timeout=45):
    """Try each endpoint in order; return the first successful reply. Returns
    None only if every endpoint fails (fail-open caller behaviour unchanged)."""
    last = None
    for endpoint in settings:
        try:
            return _chat(endpoint, messages, max_tokens=max_tokens, timeout=timeout)
        except Exception as exc:
            last = exc
    _ = last  # not logged: the key and endpoint are in it
    return None


def _clean_json(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no json object")
    return json.loads(raw[start:end + 1])


def ask_intent(text, base_url=None, api_key=None, model=None, timeout=45):
    """Parse a free-text message. Returns {"intent","topic","capital"} or None."""
    if not text or not text.strip():
        return None
    endpoints = _endpoints(base_url, api_key, model)
    if not endpoints:
        return None
    try:
        raw = _chat_failover(endpoints, [{"role": "user", "content": INTENT_PROMPT + text[:400]}], max_tokens=60, timeout=timeout)
    except Exception:
        return None
    if not raw:
        return None
    try:
        payload = _clean_json(raw)
    except Exception:
        return None
    intent = payload.get("intent")
    topic = payload.get("topic")
    capital = payload.get("capital")
    if intent not in ("research", "search", "report", "home", "help", "chat"):
        return None
    if intent in ("research", "report") and not (isinstance(topic, str) and topic.strip()):
        return None
    if capital not in BANDS:
        capital = "all"
    return {"intent": intent,
            "topic": str(topic)[:120] if isinstance(topic, str) and topic.strip() else None,
            "capital": capital}


def synthesize(query, result, max_chars=900, base_url=None, api_key=None, model=None, timeout=60):
    """AI synthesis paragraph over the deterministic result. Returns str or None."""
    endpoints = _endpoints(base_url, api_key, model)
    if not endpoints:
        return None
    candidates = result.get("candidates") or []
    if not candidates:
        return None
    lines = []
    for i, c in enumerate(candidates[:8], 1):
        v = c.get("verification") or {}
        lines.append("%d. %s | score %s/100 | %s | %s" % (
            i, c.get("title", ""), (c.get("score") or {}).get("total", "?"),
            "source-verified" if v.get("verified") else "review-required",
            c.get("source_url", "no link")))
    evidence = ("TOPIC: %s\nCOUNTRY: %s\nCAPITAL BAND: %s\n"
                "SOURCE ERRORS: %d\nGAP HITS (round 2): %s\nCANDIDATES:\n%s" % (
                    (result.get("plan") or {}).get("query", query),
                    (result.get("plan") or {}).get("country", ""),
                    (result.get("plan") or {}).get("capital", "all"),
                    len(result.get("errors") or []),
                    json.dumps(result.get("gap_hits") or {}),
                    "\n".join(lines)))
    prompt = ("Write the synthesis now.\n\nEVIDENCE:\n" + evidence[:6000])
    try:
        text = _chat_failover(endpoints, [
            {"role": "system", "content": SYSTEM_SYNTH},
            {"role": "user", "content": prompt},
        ], max_tokens=400, timeout=timeout)
    except Exception:
        return None
    if not text:
        return None
    return re.sub(r"\s+", " ", text)[:max_chars]
