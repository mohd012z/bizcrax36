"""BizCrax36 Telegram bot, stdlib only. Read-only search; token never logged.

Start with TELEGRAM_BOT_TOKEN environment variable. Optional TELEGRAM_ALLOWED_CHAT_IDS
is a comma-separated list of permitted numeric chat IDs. Without it, bot denies
all requests (fail-closed). No webhook or public listener required.
"""
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from backend.search_api import load_records
from backend.unified_search import one_search
from pathlib import Path

BASE=Path(__file__).resolve().parent.parent
MAX_RESULTS=5

def allowed(chat_id, configured):
    ids={s.strip() for s in configured.split(",") if s.strip()}
    return str(chat_id) in ids and bool(ids)

def search_text(message, database, ideas):
    parts=message.strip().split(maxsplit=1)
    command=parts[0].split("@",1)[0].lower() if parts else ""
    if command in ("/start","/help"):
        return "BizCrax36 research bot. Commands: /search keyword, /ideas keyword, /live keyword, /status. Results are research leads; verify directly with issuers."
    if command=="/status":
        return "BizCrax36 read-only search active. Live tender status requires current issuer verification."
    if command not in ("/search","/ideas","/live"):
        return "Unknown command. Send /help."
    query=parts[1].strip() if len(parts)>1 else ""
    if not query or len(query)>120:
        return "Enter a search keyword (1–120 characters). Example: /search energy"
    mode={"/search":"all","/ideas":"ideas","/live":"live"}[command]
    results=one_search(load_records(database),ideas,query=query,mode=mode)["results"]
    if not results:
        return "No matching audited results. Try another keyword. No live status is inferred."
    lines=[f"BizCrax36: {len(results)} matching results (showing up to {MAX_RESULTS})"]
    for i,r in enumerate(results[:MAX_RESULTS],1):
        title=str(r.get("title") or "Untitled").replace("\n"," ")[:110]
        state=r.get("status","review_required")
        url=r.get("source_url")
        lines.append(f"{i}. {title}\nStatus: {state}"+(f"\nSource: {url}" if isinstance(url,str) and url.startswith("https://") else ""))
    lines.append("Verify source, deadline, eligibility and costs before acting.")
    return "\n\n".join(lines)[:3800]

def api(token, method, payload):
    req=Request(f"https://api.telegram.org/bot{token}/{method}",
        data=urlencode(payload).encode("utf-8"),method="POST")
    with urlopen(req,timeout=35) as response:
        raw=response.read(1_000_000)
    data=json.loads(raw)
    if not data.get("ok"):
        raise RuntimeError("Telegram API rejected request")
    return data["result"]

def run():
    token=os.environ.get("TELEGRAM_BOT_TOKEN","")
    ids=os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS","")
    if not token or not ids:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS")
    db=Path(os.environ.get("BIZCRAX_DATABASE",str(BASE/"data/research.sqlite3")))
    ideas=[]
    for name in ("business_ideas.json","web_research_ideas.json"):
        path=BASE/"data"/name
        if path.exists():
            ideas.extend(json.loads(path.read_text(encoding="utf-8")))
    offset=0
    while True:
        try:
            updates=api(token,"getUpdates",{"timeout":25,"offset":offset,"allowed_updates":json.dumps(["message"])})
            for update in updates:
                offset=max(offset,int(update["update_id"])+1)
                message=update.get("message",{})
                chat=message.get("chat",{})
                chat_id=chat.get("id")
                if not allowed(chat_id,ids) or not isinstance(message.get("text"),str):
                    continue
                response=search_text(message["text"],db,ideas)
                api(token,"sendMessage",{"chat_id":chat_id,"text":response,"disable_web_page_preview":"true"})
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            # Never include token, request URLs, or raw responses in logs.
            print("Telegram polling error:",type(exc).__name__,flush=True)
            time.sleep(5)

if __name__=="__main__":
    run()
