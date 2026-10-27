"""BizCrax agent study & learning — the bot studies every research the user runs.

Each completed research is recorded as a *study*: topic domain, capital band,
lead/verification yield. The agent earns XP (levels up at 150 XP), and saves a
durable *skill note* per study — deterministic by default, Minda-distilled
when the AI flow is active (fail-open). State lives in the repository at
data/agent-skills/state.json (same durability pattern as research jobs) so it
survives ephemeral GitHub Actions runners. Stdlib only; never fatal.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.telegram_bot import BASE
from backend import ai_bizcollector

STATE_PATH = BASE / "data" / "agent-skills" / "state.json"
SKILLS_DIR = STATE_PATH.parent
XP_PER_LEVEL = 150
MAX_SKILLS = 40

# (domain, keywords) — first match wins; order matters (agri before technology
# so "agritech" lands in agri, not tech).
DOMAINS = (
    ("food", ("food", "restaurant", "catering", "coffee", "beverage", "bakery",
              "hawker", "snack", "dessert", "juice", "kopi", "f & b", "franchise",
              "kitchen", "food stall")),
    ("agri", ("agri", "farm", "crop", "aqua", "livestock", "orchard",
              "plantation", "poultry", "halal meat", "vertical farm")),
    ("energy", ("solar", "energy", "electrical", "pv ", "battery", "renewable",
                "charging station", "efficiency")),
    ("technology", ("app", "software", "saas", "tech", "ai", " it", "web",
                    "data", "cyber", "digital", "automation", "it ")),
    ("services", ("cleaning", "laundry", "maintenance", "repair", "consultancy",
                  "training", "education", "tutor", "logistics service", "agency")),
    ("ecommerce", ("e-commerce", "ecommerce", "online shop", "dropship",
                   "social media selling", "retail", "marketplace")),
    ("finance", ("insurance", "investment", "finance", "lending", "takaful",
                 "wealth", "accounting")),
    ("logistics", ("logistics", "delivery", "courier", "freight", "warehouse",
                   "cold chain", "last mile")),
    ("wellness", ("gym", "fitness", "spa", "beauty", "salon", "health",
                  "medical", "clinic", "supplement")),
)

LESSON_SYSTEM = (
    "You are the study module of the BizCrax business research agent. "
    "Write ONE durable skill note (max 200 characters, plain text) about the "
    "research given: what worked (useful queries or sources), what gaps or "
    "weak signals appeared, and one concrete tip for the next research. "
    "Use only the evidence provided. No markdown, no preamble."
)


def _default_state():
    return {"version": 1, "xp": 0, "studies": 0,
            "domains": {}, "bands": {}, "skills": []}


def load_state(path=STATE_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("xp"), int):
            data.setdefault("domains", {})
            data.setdefault("bands", {})
            data.setdefault("skills", [])
            return data
    except (OSError, ValueError):
        pass
    return _default_state()


def save_state(state, path=STATE_PATH):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, str(p))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def domain_of(topic):
    t = " " + str(topic or "").lower() + " "
    for name, kws in DOMAINS:
        if any(kw in t for kw in kws):
            return name
    return "other"


def level_of(xp):
    return max(1, int(xp) // XP_PER_LEVEL + 1)


def deterministic_lesson(topic, capital, result):
    candidates = result.get("candidates") or []
    n = len(candidates)
    verified = sum(1 for c in candidates if (c.get("verification") or {}).get("verified"))
    errs = len(result.get("errors") or [])
    parts = ["%d leads, %d source-verified" % (n, verified)]
    if n and verified == 0:
        parts.append("no verified sources — prefer direct publisher links over news wrappers")
    if errs:
        parts.append("%d source errors — retry later or widen queries" % errs)
    if candidates:
        top = candidates[0]
        parts.append("top signal: %s (%s/100)" % (
            str(top.get("title", ""))[:48], (top.get("score") or {}).get("total", "?")))
    return "; ".join(parts)[:220]


def _ai_lesson(topic, capital, result, base_url=None, api_key=None, model=None, timeout=20):
    """Minda-distilled skill note. Fail-open: returns None on any problem."""
    try:
        settings = ai_bizcollector._minda_settings(base_url, api_key, model)
        if not settings:
            return None
        candidates = (result.get("candidates") or [])[:5]
        lines = ["%d. %s (%s/100, %s)" % (
            i, str(c.get("title", ""))[:60], (c.get("score") or {}).get("total", "?"),
            "verified" if (c.get("verification") or {}).get("verified") else "review")
            for i, c in enumerate(candidates, 1)]
        prompt = ("TOPIC: %s\nBAND: %s\nLEADS: %d\nSOURCE-VERIFIED: %d\nSOURCE ERRORS: %d\n"
                  "CANDIDATES:\n%s" % (
                      topic, capital, len(result.get("candidates") or []),
                      sum(1 for c in (result.get("candidates") or [])
                          if (c.get("verification") or {}).get("verified")),
                      len(result.get("errors") or []), "\n".join(lines) or "(none)"))
        text = ai_bizcollector._chat(settings, [
            {"role": "system", "content": LESSON_SYSTEM},
            {"role": "user", "content": prompt},
        ], max_tokens=120, timeout=timeout)
        text = re.sub(r"\s+", " ", text or "").strip()
        return text[:220] or None
    except Exception:
        return None


def record_study(topic, capital, result, *, new=True, path=STATE_PATH, ai=False,
                 base_url=None, api_key=None, model=None):
    """Record one research session. Returns the XP outcome dict (never raises)."""
    try:
        state = load_state(path)
        domain = domain_of(topic)
        candidates = result.get("candidates") or []
        effective = len(candidates) >= 3
        new_domain = new and int(state["domains"].get(domain, 0)) == 0
        if new:
            xp_gain = 10 + (5 if effective else 0) + (25 if new_domain else 0)
        else:
            xp_gain = 2
        lesson = _ai_lesson(topic, capital, result, base_url, api_key, model) if (new and ai) else None
        ai_lesson = bool(lesson)
        if not lesson:
            lesson = deterministic_lesson(topic, capital, result)
        state["xp"] = int(state["xp"]) + xp_gain
        state["studies"] = int(state["studies"]) + 1
        state["domains"][domain] = int(state["domains"].get(domain, 0)) + 1
        band = str(capital) if capital in ("micro", "small", "medium", "large") else "all"
        state["bands"][band] = int(state["bands"].get(band, 0)) + 1
        state["skills"].insert(0, {
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "topic": str(topic)[:80], "domain": domain, "band": band,
            "leads": len(candidates),
            "verified": sum(1 for c in candidates if (c.get("verification") or {}).get("verified")),
            "level": level_of(state["xp"]), "ai": ai_lesson, "lesson": lesson,
        })
        state["skills"] = state["skills"][:MAX_SKILLS]
        save_state(state, path)
        return {"xp_gain": xp_gain, "xp": state["xp"],
                "progress": state["xp"] % XP_PER_LEVEL, "level": level_of(state["xp"]),
                "domain": domain, "new_domain": new_domain, "ai_lesson": ai_lesson}
    except Exception:
        return {"xp_gain": 0, "xp": 0, "progress": 0, "level": 1,
                "domain": "other", "new_domain": False, "ai_lesson": False}


def state_text(path=STATE_PATH):
    state = load_state(path)
    lines = ["🧠 BizCrax Agent — Level %d (%d/%d XP)" % (
        level_of(state["xp"]), int(state["xp"]) % XP_PER_LEVEL, XP_PER_LEVEL),
        "📚 Studies: %d research sessions" % int(state["studies"])]
    domains = state.get("domains") or {}
    if domains:
        lines.append("🎯 Domains studied:")
        for name, count in sorted(domains.items(), key=lambda kv: -int(kv[1])):
            lines.append("  %s %s (%d)" % (name, "▮" * min(int(count), 10), int(count)))
    bands = state.get("bands") or {}
    if bands:
        lines.append("💰 Capital focus: " + ", ".join(
            "%s (%d)" % (b, int(n)) for b, n in sorted(bands.items(), key=lambda kv: -int(kv[1]))))
    skills = state.get("skills") or []
    if skills:
        lines.append("🧩 Saved skills (latest %d of %d):" % (min(6, len(skills)), len(skills)))
        for s in skills[:6]:
            tag = "AI" if s.get("ai") else "v2"
            lines.append("• [%s] %s/%s — %s" % (
                tag, s.get("domain", "?"), s.get("band", "?"), s.get("lesson", "")))
    else:
        lines.append("🧩 No skills yet — run /research or /ai and the agent starts learning.")
    return "\n".join(lines)[:4000]


def study_menu():
    return json.dumps({"inline_keyboard": [[
        {"text": "🔁 New research", "callback_data": "bc:research"},
        {"text": "🏠 Main menu", "callback_data": "bc:home"},
    ]]}, separators=(",", ":"))
