"""Single-consumer Telegram long-poll worker with menu, uploads and exports.

Run only on an always-on host: python -m backend.telegram_live_free
Do not run concurrently with telegram_poll_once or another webhook.
"""
import io
import json
import os
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from backend.free_reliability import UpdateLedger, command_payload, export_data, import_data
from backend.telegram_bot import BASE, allowed, api
from backend.telegram_poll_once import load_ideas, process_update
from backend.telegram_menu import home

MAX_FILE = 2_000_000
MENU = json.dumps({"inline_keyboard": [
    [{"text":"🔎 Research", "callback_data":"bc:research"}, {"text":"🤖 AI", "callback_data":"bc:aimenu"}],
    [{"text":"📰 News", "callback_data":"bc:news"}, {"text":"🧠 Agent", "callback_data":"bc:study"}],
    [{"text":"📚 Records", "callback_data":"bc:mode:all"}, {"text":"🏷 Sectors", "callback_data":"bc:sectors"}],
    [{"text":"📤 Upload help", "callback_data":"bc:uploadhelp"}, {"text":"📥 Export help", "callback_data":"bc:exporthelp"}],
    [{"text":"🏠 Home", "callback_data":"bc:home"}]
]})

def register(token, transport=api):
    transport(token, "setMyCommands", {"commands":json.dumps(command_payload())})
    return transport(token, "getMyCommands", {})

def _multipart(token, chat_id, filename, data, caption="", opener=urlopen):
    boundary="BizCraxBoundary"
    def field(name, value):
        return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
    head=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
    payload=field("chat_id",chat_id)+field("caption",caption)+head+data+b"\r\n"+f"--{boundary}--\r\n".encode()
    req=Request(f"https://api.telegram.org/bot{token}/sendDocument",data=payload,
                headers={"Content-Type":f"multipart/form-data; boundary={boundary}"},method="POST")
    with opener(req,timeout=35) as response:
        result=json.load(response)
    if not result.get("ok"):
        raise RuntimeError("Telegram document delivery failed")
    return result

def _download(token, file_id, transport=api, opener=urlopen):
    info=transport(token,"getFile",{"file_id":file_id})
    if int(info.get("file_size",0))>MAX_FILE:
        raise ValueError("file exceeds 2MB limit")
    path=info.get("file_path","")
    if not path or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid Telegram file path")
    req=Request(f"https://api.telegram.org/file/bot{token}/{quote(path,safe='/')}")
    with opener(req,timeout=30) as response:
        data=response.read(MAX_FILE+1)
    if len(data)>MAX_FILE:
        raise ValueError("file exceeds 2MB limit")
    return data

def process_live(update, *, token, allowed_ids, database, ideas, send=None,
                 download=None, upload=None, store=None):
    send=send or (lambda method,payload: api(token,method,payload))
    download=download or (lambda file_id: _download(token,file_id))
    upload=upload or (lambda chat_id,name,data,caption: _multipart(token,chat_id,name,data,caption))
    message=update.get("message") or {}
    callback=update.get("callback_query") or {}
    chat_id=(message.get("chat") or callback.get("message",{}).get("chat") or {}).get("id")
    if not allowed(chat_id,allowed_ids):
        return "denied"
    if callback.get("data") in ("bc:uploadhelp","bc:exporthelp"):
        send("answerCallbackQuery",{"callback_query_id":callback["id"]})
        instruction=("📤 Send a JSON or CSV document (max 2MB). Records are validated and returned as a receipt."
                     if callback["data"]=="bc:uploadhelp" else
                     "📥 Send /export json or /export csv to download your last imported records.")
        send("sendMessage",{"chat_id":chat_id,"text":instruction,"reply_markup":MENU})
        return "sent"
    document=message.get("document")
    text=(message.get("text") or "").strip()
    if document:
        filename=Path(document.get("file_name","")).name
        extension=Path(filename).suffix.lower()
        if extension not in (".json",".csv"):
            send("sendMessage",{"chat_id":chat_id,"text":"Supported uploads: JSON and CSV only."})
            return "sent"
        try:
            if int(document.get("file_size",0))>MAX_FILE:
                raise ValueError("file exceeds 2MB")
            rows=import_data(download(document["file_id"]),extension)
            if store is not None:
                store[chat_id]=rows
            send("sendMessage",{"chat_id":chat_id,"text":f"✅ Validated {len(rows)} records from {filename}. No existing research overwritten.","reply_markup":MENU})
        except (ValueError,KeyError,UnicodeError) as exc:
            send("sendMessage",{"chat_id":chat_id,"text":f"❌ Import rejected: {str(exc)[:180]}"})
        return "sent"
    if text.lower().split(maxsplit=1)[0:1] == ["/export"]:
        ext=".csv" if text.lower().split()[-1:] == ["csv"] else ".json"
        rows=(store or {}).get(chat_id,[])
        upload(chat_id,"bizcrax-export"+ext,export_data(rows,ext),f"Validated records: {len(rows)}")
        return "sent"
    if text.lower().split(maxsplit=1)[0:1] in (["/import"],["/documents"]):
        send("sendMessage",{"chat_id":chat_id,"text":"Send a JSON or CSV document up to 2MB. Use /export json or /export csv afterward.","reply_markup":MENU})
        return "sent"
    if text.lower().split(maxsplit=1)[0:1] in (["/start"],["/help"]):
        send("sendMessage",{"chat_id":chat_id,"text":"BizCrax36 • Research Control Center\nChoose a category or send /research <topic>.","reply_markup":MENU})
        return "sent"
    return process_update(update,send=send,allowed_ids=allowed_ids,database=database,ideas=ideas,token=token)

def main():
    token=os.environ["TELEGRAM_BOT_TOKEN"]
    allowed_ids=os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") or os.environ["TELEGRAM_CHAT_ID"]
    webhook=api(token,"getWebhookInfo",{})
    if webhook.get("url"):
        raise SystemExit("Webhook active; stop it before starting a polling worker.")
    print("Registered commands:",register(token),flush=True)
    ledger_path=Path(os.environ.get("BIZCRAX_UPDATE_DB","data/telegram_updates.sqlite3"))\n    ledger_path.parent.mkdir(parents=True,exist_ok=True)\n    ledger=UpdateLedger(ledger_path)
    records={}
    ideas=load_ideas()
    offset=None
    while True:
        try:
            payload={"timeout":25,"limit":25,"allowed_updates":json.dumps(["message","callback_query"])}
            if offset is not None:
                payload["offset"]=offset
            for update in api(token,"getUpdates",payload):
                uid=update["update_id"]
                if not ledger.seen(uid):
                    process_live(update,token=token,allowed_ids=allowed_ids,
                                 database=BASE/"data"/"research.sqlite3",ideas=ideas,store=records)
                    ledger.mark(uid)
                offset=uid+1
        except Exception as exc:
            print("polling error:",type(exc).__name__,str(exc)[:150],flush=True)
            time.sleep(3)

if __name__=="__main__":
    main()
