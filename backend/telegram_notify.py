"""One-shot Telegram notification for GitHub Actions (no long-running polling).

Only sends to TELEGRAM_CHAT_ID, and never prints credentials.
"""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from backend.search_api import load_records
from backend.unified_search import one_search
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def build_digest(database, ideas, query=""):
    result=one_search(load_records(database),ideas,query=query,mode="all")
    rows=result["results"]
    lines=["BizCrax36 research update",f"Matching research leads: {len(rows)}"]
    for row in rows[:5]:
        title=str(row.get("title") or "Untitled").replace("\n"," ")[:100]
        lines.append(f"• {title} [{row.get('status','review_required')}]")
        url=row.get("source_url")
        if isinstance(url,str) and url.startswith("https://"):
            lines.append(url)
    lines.append("Research ideas are unverified. Confirm issuer status, eligibility and deadlines independently.")
    return "\n".join(lines)[:3800]

def send(token, chat_id, message, opener=urlopen):
    if not token or not chat_id or not message:
        raise ValueError("Telegram credentials or message missing")
    request=Request("https://api.telegram.org/bot"+token+"/sendMessage",
        data=urlencode({"chat_id":chat_id,"text":message,
                        "disable_web_page_preview":"true"}).encode(),
        method="POST")
    with opener(request,timeout=25) as response:
        data=json.loads(response.read(100000))
    if data.get("ok") is not True:
        raise RuntimeError("Telegram rejected sendMessage")
    return True

def main():
    token=os.environ.get("TELEGRAM_BOT_TOKEN","")
    chat_id=os.environ.get("TELEGRAM_CHAT_ID","")
    if not token or not chat_id:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID GitHub secret")
    ideas=[]
    for name in ("business_ideas.json","web_research_ideas.json"):
        path=ROOT/"data"/name
        if path.exists():
            ideas.extend(json.loads(path.read_text(encoding="utf-8")))
    database=Path(os.environ.get("BIZCRAX_DATABASE",str(ROOT/"data/research.sqlite3")))
    message=build_digest(database,ideas,os.environ.get("BIZCRAX_QUERY",""))
    send(token,chat_id,message)
    print("Telegram notification delivered to configured chat")

if __name__=="__main__":
    main()
