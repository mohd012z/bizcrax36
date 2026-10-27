"""Telegram inline-button menus for BizCrax36, inspired by kutepboku pagination.

Telegram has no native dropdown widget; inline keyboard submenus serve that role.
Callbacks are short, stateless and restricted to a fixed allowlist.
"""
import json

SECTORS=("All","Technology","Industrial","Energy","Aviation","Services")
MODES=("all","ideas","live","review")

def keyboard(rows):
    return json.dumps({"inline_keyboard":rows},separators=(",",":"))

def home():
    return keyboard([
        [{"text":"🔎 Search opportunities","callback_data":"bc:search"},
         {"text":"💡 Business ideas","callback_data":"bc:mode:ideas"}],
        [{"text":"📋 All research","callback_data":"bc:mode:all"},
         {"text":"✅ Verified live","callback_data":"bc:mode:live"}],
        [{"text":"🏷 Sector ▾","callback_data":"bc:sectors"},
         {"text":"🔍 Review required","callback_data":"bc:mode:review"}],
        [{"text":"ℹ️ Help","callback_data":"bc:help"}]
    ])

def sectors():
    rows=[[{"text":name,"callback_data":"bc:sector:"+str(i)}] for i,name in enumerate(SECTORS)]
    rows.append([{"text":"◀ Back","callback_data":"bc:home"}])
    return keyboard(rows)

def paged_menu(kind, value, index, pages):
    if kind not in ("mode","sector"):
        raise ValueError("invalid pagination kind")
    if kind=="mode" and value not in MODES:
        raise ValueError("invalid mode")
    if kind=="sector" and (not value.isdigit() or int(value)>=len(SECTORS)):
        raise ValueError("invalid sector")
    base=f"bc:page:{kind}:{value}:"
    controls=[]
    if index>0:
        controls.append({"text":"◀ Previous","callback_data":base+str(index-1)})
    if index+1<pages:
        controls.append({"text":"Next ▶","callback_data":base+str(index+1)})
    rows=[controls] if controls else []
    rows.append([{"text":"🏠 Main menu","callback_data":"bc:home"}])
    return keyboard(rows)

def results_menu(mode,sector=""):
    return keyboard([
        [{"text":"🔄 Refresh","callback_data":"bc:mode:"+mode}],
        [{"text":"🏷 Sector ▾","callback_data":"bc:sectors"},
         {"text":"🏠 Main menu","callback_data":"bc:home"}]
    ])

def resolve(data):
    if data in ("bc:home","bc:help","bc:search","bc:sectors"):
        return data
    if data.startswith("bc:mode:") and data[8:] in MODES:
        return data
    if data.startswith("bc:page:"):
        parts=data.split(":")
        if len(parts)==5 and parts[2] in ("mode","sector") and parts[4].isdigit() and len(parts[4])<=5:
            value=parts[3]
            if parts[2]=="mode" and value in MODES:
                return data
            if parts[2]=="sector" and value.isdigit() and int(value)<len(SECTORS):
                return data
        return None
    if data.startswith("bc:sector:") and data[10:].isdigit():
        i=int(data[10:])
        if 0<=i<len(SECTORS):
            return data
    return None
