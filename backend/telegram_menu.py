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
        [{"text":"🤖 AI bizcollector","callback_data":"bc:aimenu"}],
        [{"text":"🚀 Research engine","callback_data":"bc:research"},
         {"text":"📰 News agent","callback_data":"bc:news"}],
        [{"text":"🧠 Agent study","callback_data":"bc:study"},
         {"text":"🏷 Sector ▾","callback_data":"bc:sectors"}],
        [{"text":"🔎 Search opportunities","callback_data":"bc:search"},
         {"text":"💡 Business ideas","callback_data":"bc:mode:ideas"}],
        [{"text":"📋 All research","callback_data":"bc:mode:all"},
         {"text":"✅ Verified live","callback_data":"bc:mode:live"}],
        [{"text":"🔍 Review required","callback_data":"bc:mode:review"},
         {"text":"ℹ️ Help","callback_data":"bc:help"}]
    ])

def news_menu():
    return keyboard([
        [{"text":"📰 Scan all latest news","callback_data":"bc:news:scan:all:1"}],
        [{"text":"🤖 AI","callback_data":"bc:news:scan:ai:1"},
         {"text":"🪙 Crypto","callback_data":"bc:news:scan:crypto:1"}],
        [{"text":"🚀 Startups","callback_data":"bc:news:scan:startup:1"},
         {"text":"🛒 E-commerce","callback_data":"bc:news:scan:ecommerce:1"}],
        [{"text":"🍜 F&B / Halal","callback_data":"bc:news:scan:food:1"},
         {"text":"🏢 Property","callback_data":"bc:news:scan:realestate:1"}],
        [{"text":"⚡ Energy / EV","callback_data":"bc:news:scan:energy:1"},
         {"text":"📋 Tenders","callback_data":"bc:news:scan:tender:1"}],
        [{"text":"🧩 Business plan from top research","callback_data":"bc:news:plan"}],
        [{"text":"💬 How to use (paste a news link)","callback_data":"bc:news"},
         {"text":"🏠 Main menu","callback_data":"bc:home"}]
    ])

def news_page_menu(topic, page, has_prev, has_next):
    """Prev/Next + filter switcher for a paginated news scan."""
    t = topic or "all"
    rows = []
    nav = []
    if has_prev:
        nav.append({"text":"⬅️ Back","callback_data":"bc:news:scan:%s:%d"%(t,page-1)})
    if has_next:
        nav.append({"text":"Next ➡️","callback_data":"bc:news:scan:%s:%d"%(t,page+1)})
    if nav:
        rows.append(nav)
    rows.append([
        {"text":"📰 All","callback_data":"bc:news:scan:all:%d"%page},
        {"text":"🤖 AI","callback_data":"bc:news:scan:ai:%d"%page},
        {"text":"🪙 Crypto","callback_data":"bc:news:scan:crypto:%d"%page},
    ])
    rows.append([
        {"text":"🚀 Startups","callback_data":"bc:news:scan:startup:%d"%page},
        {"text":"🛒 E-comm","callback_data":"bc:news:scan:ecommerce:%d"%page},
        {"text":"🍜 F&B","callback_data":"bc:news:scan:food:%d"%page},
    ])
    rows.append([
        {"text":"🏢 Property","callback_data":"bc:news:scan:realestate:%d"%page},
        {"text":"⚡ Energy","callback_data":"bc:news:scan:energy:%d"%page},
        {"text":"📋 Tenders","callback_data":"bc:news:scan:tender:%d"%page},
    ])
    rows.append([{"text":"🏠 Main menu","callback_data":"bc:home"}])
    return keyboard(rows)

def research_help():
    return keyboard([
        [{"text":"💬 How to use","callback_data":"bc:research"}],
        [{"text":"🏠 Main menu","callback_data":"bc:home"}]
    ])

def report_menu(job_id):
    return keyboard([
        [{"text":"📄 Report (DOCX)","callback_data":"bc:report:%s"%job_id}],
        [{"text":"🔁 New research","callback_data":"bc:research"},
         {"text":"🏠 Main menu","callback_data":"bc:home"}]
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

def _valid_job_id(value):
    return len(value)==12 and all(c in "0123456789abcdef" for c in value.lower())

def resolve(data):
    if data in ("bc:home","bc:help","bc:search","bc:sectors","bc:research","bc:study"):
        return data
    if data.startswith("bc:report:") and _valid_job_id(data[10:]):
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
