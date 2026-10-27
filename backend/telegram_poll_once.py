"""Bounded Telegram update processor for GitHub Actions.

Telegram stores pending updates; explicit getUpdates(offset=last+1) acknowledges
each successfully handled update. No Git commits or mutable runner state needed.
Delivery and acknowledgement are not atomic: a crash may cause one duplicate.
"""
import json
import os
from urllib.error import HTTPError
from pathlib import Path
from backend.telegram_bot import api,allowed,search_text,handle_callback,BASE
from backend.telegram_menu import home, sectors
from backend.telegram_result_utils import deduplicate_ideas
from backend.agentic_research import research

def load_ideas(root=BASE):
    ideas=[]
    for name in ("business_ideas.json","web_research_ideas.json"):
        p=root/"data"/name
        if p.exists():
            items=json.loads(p.read_text(encoding="utf-8"))
            if isinstance(items,list):
                ideas.extend(items)
    return deduplicate_ideas(ideas)

def format_research(result):
    items=result['candidates'][:5]
    lines=[f"Research: {result['plan']['query']}", f"Candidates: {len(result['candidates'])} | source errors: {len(result['errors'])}"]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['title']}\n{item['source_url']}\nStatus: REVIEW_REQUIRED")
    if not items:
        lines.append('No candidates discovered. Sources may be unavailable; try a narrower topic.')
    lines.append('News leads only; profitability, demand and tender eligibility are NOT verified.')
    return '\n\n'.join(lines)[:3900]

def safe_callback_answer(send, callback_id, **extra):
    if not callback_id:
        return
    try:
        send('answerCallbackQuery', {'callback_query_id': callback_id, **extra})
    except HTTPError as exc:
        if exc.code != 400:
            raise
        # Scheduled GitHub polling often receives callbacks after Telegram expiry.

def process_update(update, *, send, allowed_ids, database, ideas, researcher=research):
    callback=update.get("callback_query")
    if isinstance(callback,dict):
        callback_id=callback.get("id")
        chat_id=(callback.get("message") or {}).get("chat",{}).get("id")
        if not allowed(chat_id,allowed_ids):
            if callback_id:
                safe_callback_answer(send,callback_id,text="Not authorized",show_alert="true")
            return "denied"
        text,markup=handle_callback(callback.get("data",""),database,ideas)
        # Acknowledge only after successful message delivery.
        original=callback.get("message") or {}
        message_id=original.get("message_id")
        if isinstance(message_id,int):
            try:
                send("editMessageText",{"chat_id":chat_id,"message_id":message_id,
                    "text":text[:4000],"reply_markup":markup,
                    "disable_web_page_preview":"true"})
            except HTTPError as exc:
                if exc.code != 400:
                    raise
                send("sendMessage",{"chat_id":chat_id,"text":text[:4000],
                    "reply_markup":markup,"disable_web_page_preview":"true"})
        else:
            send("sendMessage",{"chat_id":chat_id,"text":text[:4000],
                "reply_markup":markup,"disable_web_page_preview":"true"})
        if callback_id:
            safe_callback_answer(send,callback_id)
        return "sent"
    message=update.get("message")
    if not isinstance(message,dict):
        return "ignored"
    chat_id=(message.get("chat") or {}).get("id")
    if not allowed(chat_id,allowed_ids):
        return "denied"
    text=message.get("text")
    if not isinstance(text,str):
        return "ignored"
    command=text.strip().split(maxsplit=1)[0].split("@",1)[0].lower() if text.strip() else ""
    if command=="/research":
        query=text.strip().partition(" ")[2].strip()
        if not query or len(query)>120:
            response="Usage: /research aviation training Malaysia (1–120 characters)."
        else:
            try:
                response=format_research(researcher(query,max_queries=3))
            except (OSError, ValueError) as exc:
                response="Research temporarily unavailable. Please try again later."
                print("Research error:",type(exc).__name__,flush=True)
    else:
        response="Select a business sector:" if command in ("/sector","/sectors") else search_text(text,database,ideas)
    markup=sectors() if command in ("/sector","/sectors") else home()
    send("sendMessage",{"chat_id":chat_id,"text":response,
        "reply_markup":markup,"disable_web_page_preview":"true"})
    return "sent"

def poll_once(token,allowed_ids,database,ideas,telegram_api=api,max_updates=50):
    if not token or not allowed_ids:
        raise ValueError("Telegram credentials missing")
    def call(method,payload):
        return telegram_api(token,method,payload)
    # Use zero timeout: GitHub Actions is not a permanent bot host.
    updates=call("getUpdates",{"timeout":0,"limit":max_updates,
        "allowed_updates":json.dumps(["message","callback_query"])})
    processed=0
    outcomes={"sent":0,"denied":0,"ignored":0,"suppressed":0}
    # Collapse repeated /start messages from the same chat in this batch.
    # Preserve the newest /start and all other commands and button callbacks.
    newest_start={}
    for update in updates:
        message=update.get("message") if isinstance(update,dict) else None
        if isinstance(message,dict) and str(message.get("text","")).strip().split("@")[0]=="/start":
            chat_id=(message.get("chat") or {}).get("id")
            newest_start[chat_id]=update.get("update_id")
    suppressed=0
    for update in updates:
        if not isinstance(update,dict) or not isinstance(update.get("update_id"),int):
            raise ValueError("invalid Telegram update")
        message=update.get("message")
        is_start=isinstance(message,dict) and str(message.get("text","")).strip().split("@")[0]=="/start"
        chat_id=(message.get("chat") or {}).get("id") if isinstance(message,dict) else None
        if is_start and newest_start.get(chat_id)!=update["update_id"]:
            suppressed+=1
            outcomes["suppressed"]+=1
        else:
            outcome=process_update(update,send=call,allowed_ids=allowed_ids,database=database,ideas=ideas)
            outcomes[outcome]=outcomes.get(outcome,0)+1
        # Telegram confirms updates strictly below offset. This avoids replay
        # across ephemeral GitHub runners. A failed send stops before ack.
        call("getUpdates",{"timeout":0,"limit":1,"offset":update["update_id"]+1,
            "allowed_updates":json.dumps(["message","callback_query"])})
        processed+=1
    print("Telegram diagnostic: "+json.dumps({"received":len(updates),"acknowledged":processed,**outcomes},sort_keys=True),flush=True)
    return processed

def main():
    token=os.environ.get("TELEGRAM_BOT_TOKEN","")
    allowed_ids=os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") or os.environ.get("TELEGRAM_CHAT_ID","")
    if not token or not allowed_ids:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    db=Path(os.environ.get("BIZCRAX_DATABASE",str(BASE/"data/research.sqlite3")))
    webhook=api(token,"getWebhookInfo",{})
    if webhook.get("url"):
        raise SystemExit("Telegram webhook is active: getUpdates polling cannot operate until webhook is disabled on the bot owner account")
    print("Telegram webhook: inactive; polling enabled",flush=True)
    count=poll_once(token,allowed_ids,db,load_ideas())
    print(f"Telegram updates processed: {count}")

if __name__=="__main__":
    main()
