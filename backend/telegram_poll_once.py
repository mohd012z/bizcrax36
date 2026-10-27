"""Bounded Telegram update processor for GitHub Actions — Agentic Research V2.

Fast-response flow: the bot acknowledges /research instantly, runs the staged
V2 engine (discovery rounds → verification → scoring), then delivers a
360° summary with a one-tap DOCX report button. Completed jobs are persisted
to the repository under data/research-jobs/ (git push) so a later polling run
on a fresh ephemeral runner can still send the stored report on button tap.

Telegram stores pending updates; explicit getUpdates(offset=last+1)
acknowledges each successfully handled update. Delivery and acknowledgement
are not atomic: a crash may cause one duplicate.
"""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.telegram_bot import api,allowed,search_text,handle_callback,BASE
from backend.telegram_menu import home, sectors, research_help, report_menu, news_menu
from backend.telegram_result_utils import deduplicate_ideas
from backend.dossier import build as build_dossier, summary_text
from backend.research_queue import run_job, is_duplicate, diagnostics_line, validate_topic
from backend.reports import generate_report, generate_news_report
from backend import ai_bizcollector, agent_skill, news_agent

JOBS_DIR=BASE/"data"/"research-jobs"

def load_ideas(root=BASE):
    ideas=[]
    for name in ("business_ideas.json","web_research_ideas.json"):
        p=root/"data"/name
        if p.exists():
            items=json.loads(p.read_text(encoding="utf-8"))
            if isinstance(items,list):
                ideas.extend(items)
    return deduplicate_ideas(ideas)

def _utcnow():
    return datetime.now(timezone.utc)

# ------------------------------------------------------------------ job store

def job_dir(job_id):
    return JOBS_DIR/job_id

def load_job(job_id):
    if job_id is None:
        return None
    path=job_dir(job_id)/"job.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None

def list_completed_jobs():
    jobs=[]
    if not JOBS_DIR.exists():
        return jobs
    for path in sorted(JOBS_DIR.glob("*/job.json")):
        try:
            job=json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if job.get("status")=="completed":
            jobs.append(job)
    return jobs

def save_job(job, result, report_paths):
    d=job_dir(job["id"])
    d.mkdir(parents=True,exist_ok=True)
    payload={"id":job["id"],"query":job["query"],"country":job["country"],
             "capital":job["capital"],"status":job["status"],
             "created_at":job["created_at"],"finished_at":job.get("finished_at"),
             "duration_seconds":job.get("duration_seconds"),
             "diagnostics":job.get("diagnostics"),"error":job.get("error"),
             "result":result,"report":report_paths}
    (d/"job.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    return d

def _git(cwd,*args):
    env=dict(os.environ)
    env["GIT_TERMINAL_PROMPT"]="0"
    completed=subprocess.run(["git",*args],cwd=str(cwd),env=env,
                             capture_output=True,text=True,timeout=120)
    if completed.returncode!=0:
        raise RuntimeError("git %s failed: %s"%(args[0],completed.stderr.strip()[:200]))
    return completed.stdout.strip()

def persist_jobs(repository,token,base=BASE):
    """Commit and push new research jobs so later runners can serve them. Fail-open."""
    if not repository or not token:
        return False
    if not JOBS_DIR.exists() or not list(JOBS_DIR.glob("*/job.json")):
        return False
    try:
        _git(base,"add","data/research-jobs","data/agent-skills")
        status=subprocess.run(["git","status","--porcelain","data/research-jobs","data/agent-skills"],
                              cwd=str(base),capture_output=True,text=True).stdout
        if not status.strip():
            return False
        stamp=_utcnow().strftime("%Y-%m-%d %H:%M UTC")
        _git(base,"-c","user.name=BizCrax36 Research","-c","user.email=research@bizcrax36.local",
             "commit","-m","research: completed jobs + agent skills %s"%stamp)
        url="https://x-access-token:%s@github.com/%s.git"%(token,repository)
        _git(base,"push",url,"HEAD:main")
        return True
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        print("Job persist skipped:",type(exc).__name__,flush=True)
        return False

# ------------------------------------------------------------- report delivery

def _multipart_send(token, method, fields, file_field, file_path):
    boundary="bizcrax36boundary9f27c1"
    body=b""
    for key,value in fields.items():
        body+=("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
               %(boundary,key,value)).encode("utf-8")
    file_name=os.path.basename(str(file_path))
    body+=("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
           "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
           %(boundary,file_field,file_name)).encode("utf-8")
    body+=Path(str(file_path)).read_bytes()
    body+=("\r\n--%s--\r\n"%boundary).encode("utf-8")
    req=Request("https://api.telegram.org/bot%s/%s"%(token,method),data=body,method="POST")
    req.add_header("Content-Type","multipart/form-data; boundary=%s"%boundary)
    with urlopen(req,timeout=60) as response:
        data=json.loads(response.read(1_000_000))
    if not data.get("ok"):
        raise RuntimeError("Telegram API rejected document send")
    return data["result"]

def deliver_report(token,chat_id,job):
    """Send the stored DOCX report for a completed job. Returns True on success."""
    docx=job_dir(job["id"])/"report.docx"
    if not docx.exists():
        return False
    d=job.get("diagnostics") or {}
    caption=("360° Report — %s\n%s | %d leads | %d source-verified | top score %s/100\n"
             "All leads review_required until independently verified.")% (
        job.get("query"),job.get("country"),d.get("candidates",0),
        d.get("source_verified",0),d.get("top_score","?"))[:1000]
    _multipart_send(token,"sendDocument",
                    {"chat_id":str(chat_id),"caption":caption,
                     "disable_web_page_preview":"true"},
                    "document",docx)
    return True

# ----------------------------------------------------------------- research flow

def study_line(query,result,capital,ai):
    """Record this research as a study (fail-open) and return the XP line."""
    try:
        out=agent_skill.record_study(query,capital,result,new=True,ai=ai)
        if out["xp_gain"]>0:
            extra=" (new domain: %s)"%out["domain"] if out.get("new_domain") else ""
            return ("\n🧠 Agent studied this: +%d XP → Level %d (%d/%d)%s — skill saved."
                    %(out["xp_gain"],out["level"],out["progress"],agent_skill.XP_PER_LEVEL,extra))
    except Exception:
        pass
    return ""

def run_research(token,chat_id,send,query,capital,repository,job_token,ai=False):
    """Fast ack → staged V2 research → 360° summary → report button."""
    ack=("⚡ Research queued: %s\nCapital band: %s\n"
         "Flow: demand discovery → gap queries (competition, licensing, demand evidence) → "
         "source verification → scoring → 360° dossier.\n"
         "This ack arrives first, confirming fast response.")%(query,capital)
    send("sendMessage",{"chat_id":chat_id,"text":ack[:4000],
        "reply_markup":research_help(),"disable_web_page_preview":"true"})
    recent=is_duplicate(list_completed_jobs(),query,capital,country="Malaysia")
    if recent is not None:
        job=recent
        result=job.get("result")
    else:
        job,result,_=run_job(query,capital=capital)
    if job["status"]!="completed" or result is None:
        text=("❌ Research failed (%s). Sources may be rate-limited; try again in a few minutes."
              %job.get("error","unknown"))[:4000]
        send("sendMessage",{"chat_id":chat_id,"text":text,"reply_markup":research_help(),
            "disable_web_page_preview":"true"})
        return
    dossier=build_dossier(result)
    if recent is None:
        report_paths=generate_report(dossier,result,job_dir(job["id"]))
        save_job(job,result,report_paths)
        persist_jobs(repository,job_token)
    summary=summary_text(dossier,result)
    summary+="\n\n"+diagnostics_line(job)
    if ai:
        synthesis=ai_synthesis(query,result)
        if synthesis:
            summary=(summary+synthesis)[:4000]
    if recent is None:
        summary=(summary+study_line(query,result,capital,ai))[:4000]
    send("sendMessage",{"chat_id":chat_id,"text":summary[:4000],
        "reply_markup":report_menu(job["id"]),"disable_web_page_preview":"true"})

def handle_research_command(token,send,chat_id,body):
    query,capital=validate_topic(body)
    if not query:
        send("sendMessage",{"chat_id":chat_id,
            "text":("Usage: /research <topic> [micro|small|medium|large]\n"
                    "Example: /research energy efficiency services small\n"
                    "Instant ack → scored 360° summary → tap 📄 Report for the full DOCX dossier."),
            "reply_markup":research_help(),"disable_web_page_preview":"true"})
        return
    run_research(token,chat_id,send,query,capital,"","",ai=False)

# ------------------------------------------------------- AI bizcollector flow

AI_SHORTCUTS=[
    ("hot",  "🔥 High potential — any sector, any capital", "high potential business opportunities"),
    ("low",  "💰 Low cost starts (micro <RM10k)",           "low cost home based business ideas"),
    ("small","📈 Small investment (RM10k–250k)",            "small business opportunities"),
    ("med",  "🏗️ Medium investment (RM250k–2M)",           "medium scale business expansion"),
    ("large","🏢 Large investment (RM2M+)",                 "large scale investment opportunities"),
]

def ai_menu():
    rows=[[{"text":label,"callback_data":"bc:ai:%s"%key}] for key,label,_ in AI_SHORTCUTS]
    rows.append([{"text":"✍️ Ask AI (type a topic)","callback_data":"bc:ai:ask"}])
    rows.append([{"text":"🏠 Main menu","callback_data":"bc:home"}])
    return json.dumps({"inline_keyboard":rows},separators=(",",":"))

def ai_shortcut(key):
    for k,label,topic in AI_SHORTCUTS:
        if k==key:
            return topic
    return None

def handle_ai_command(token,send,chat_id,body):
    """AI bizcollector: Minda intent parsing (fail-open) → V2 research → AI synthesis."""
    if not body:
        intent=ai_bizcollector.ask_intent("show the business research menu")
        send("sendMessage",{"chat_id":chat_id,
            "text":("🤖 BizCrax AI — ask me ANYTHING about business opportunities, or tap a shortcut.\n"
                    "Example: /ai find a small capital food business in Malaysia\n"
                    "I parse your request with AI, run the full evidence-first research, "
                    "and add an AI synthesis. No AI? I still answer deterministically."),
            "reply_markup":ai_menu(),"disable_web_page_preview":"true"})
        return
    # Fast ack FIRST so the reply is instant; AI parsing happens right after.
    send("sendMessage",{"chat_id":chat_id,
        "text":"🤖 AI bizcollector: parsing your request…",
        "reply_markup":ai_menu(),"disable_web_page_preview":"true"})
    intent=ai_bizcollector.ask_intent(body)
    if intent and intent["intent"] in ("research","report") and intent["topic"]:
        query,capital=intent["topic"],intent["capital"]
    else:
        query,capital=validate_topic(body)
    if not query:
        send("sendMessage",{"chat_id":chat_id,
            "text":"Tell me a business topic, e.g. /ai solar maintenance small capital",
            "reply_markup":ai_menu(),"disable_web_page_preview":"true"})
        return
    run_research(token,chat_id,send,query,capital,"","",ai=True)

def ai_synthesis(query,result):
    """Best-effort AI paragraph; returns '' when Minda is unavailable (fail-open)."""
    try:
        text=ai_bizcollector.synthesize(query,result)
    except Exception:
        text=None
    if not text:
        return ""
    return "\n\n🤖 AI SYNTHESIS (Minda, FACT/INFER/ASSUME labeled):\n"+text

# ------------------------------------------------------------- news agent flow

def _news_docx_send(token, chat_id, docx, caption):
    _multipart_send(token, "sendDocument",
                    {"chat_id": str(chat_id), "caption": caption,
                     "disable_web_page_preview": "true"},
                    "document", docx)

def news_scan_text(items, errors):
    lines = ["📰 News agent — business-development scan",
             "Read %d headlines across %d feeds in a few seconds." % (
                 len(items), len({i.get("source") for i in items}))]
    if errors:
        lines.append("Feed errors (fail-open): %d" % len(errors))
    for it in items[:18]:
        lines.append("• [%s] %s" % (it.get("source", "?")[:24], it.get("title", "")[:110]))
    lines.append("")
    lines.append("👉 To build a full business plan + DOCX from one of these, "
                 "send the article link to me, or use /newsplan on your last research.")
    return "\n".join(lines)[:4000]

def news_plan_text(plan):
    sig = plan["signals"]
    b = plan["budget"]
    lines = ["🧩 Business implementation plan — %s" % plan["topic"][:90],
             "Sector: %s · Horizon: %s · Potential: %s (growth score %d)" % (
                 plan["sector"], plan["horizon"], plan["potential_class"], sig["growth_score"])]
    lines.append("Illustrative budget: RM %s (%s band)" % ("{:,}".format(b["total"]), b["band"]))
    top_risk = plan["risks"][0] if plan["risks"] else None
    if top_risk:
        lines.append("Top risk [%d/9]: %s" % (top_risk["score"], top_risk["risk"][:80]))
    lines.append("")
    lines.append("Included: live market evidence (macro), implementation flow, "
                 "budget, investment/funding routes, merger (M&A) + joint-venture "
                 "routes, marketing plan, risk register, phased 12-month plan.")
    lines.append("📄 Full DOCX attached. REVIEW_REQUIRED until assumptions confirmed.")
    return "\n".join(lines)[:4000]

def run_news_scan(token, send, chat_id):
    send("sendMessage", {"chat_id": chat_id, "text": "📰 Scanning business feeds…",
        "reply_markup": news_menu(), "disable_web_page_preview": "true"})
    try:
        items, errors = news_agent.scan(limit=25, workers=6)
    except Exception as exc:
        send("sendMessage", {"chat_id": chat_id, "text": "News scan failed: %s" % type(exc).__name__,
            "reply_markup": news_menu(), "disable_web_page_preview": "true"})
        return
    if not items:
        send("sendMessage", {"chat_id": chat_id, "text": "No news items retrieved (feeds may be "
            "rate-limited). Try again in a minute.", "reply_markup": news_menu(),
            "disable_web_page_preview": "true"})
        return
    send("sendMessage", {"chat_id": chat_id, "text": news_scan_text(items, errors),
        "reply_markup": news_menu(), "disable_web_page_preview": "true"})

def _latest_research_result():
    jobs = list_completed_jobs()
    if not jobs:
        return None
    jobs.sort(key=lambda j: j.get("finished_at") or j.get("created_at") or "")
    return jobs[-1]

def run_news_plan(token, send, chat_id, url=None, job_id=None):
    send("sendMessage", {"chat_id": chat_id, "text": "🧩 Building your business plan "
        "(reading source + live macro + budget/risk)…" if url else "🧩 Building your business "
        "plan from the top of your last research…",
        "reply_markup": news_menu(), "disable_web_page_preview": "true"})
    try:
        if url:
            article = news_agent.fetch_article(url)
            if article.get("basis") == "unavailable":
                send("sendMessage", {"chat_id": chat_id, "text": "Couldn't read that article "
                    "(%s). Try a direct publisher link (not a Google News wrapper)." %
                    article.get("error"), "reply_markup": news_menu(), "disable_web_page_preview": "true"})
                return
            plan = news_agent.implementation_plan(article, topic=article["title"][:100])
            items = []
        else:
            job = load_job(job_id) if job_id else _latest_research_result()
            if not job or job.get("status") != "completed" or not job.get("result"):
                send("sendMessage", {"chat_id": chat_id, "text": "No completed research found. "
                    "Run /research <topic> first, then /newsplan.",
                    "reply_markup": news_menu(), "disable_web_page_preview": "true"})
                return
            plan = news_agent.plan_from_result(job["result"])
            items = []
        dossier = news_agent.news_dossier(plan, items)
        out_dir = JOBS_DIR / ("newsplan-%d" % int(datetime.now(timezone.utc).timestamp()))
        paths = generate_news_report(dossier, plan, out_dir)
    except Exception as exc:
        send("sendMessage", {"chat_id": chat_id, "text": "Plan build failed: %s. Try again or "
            "send a direct article link." % type(exc).__name__,
            "reply_markup": news_menu(), "disable_web_page_preview": "true"})
        return
    send("sendMessage", {"chat_id": chat_id, "text": news_plan_text(plan),
        "reply_markup": news_menu(), "disable_web_page_preview": "true"})
    try:
        _news_docx_send(token, chat_id, paths["docx"], "Business plan DOCX — %s" % plan["topic"][:120])
    except Exception as exc:
        send("sendMessage", {"chat_id": chat_id, "text": "Plan is ready (above) but the DOCX "
            "send failed: %s" % type(exc).__name__, "reply_markup": news_menu(),
            "disable_web_page_preview": "true"})

def handle_news_command(token, send, chat_id, body):
    """`/news` = scan; `/news <url>` = plan from that article; `/newsplan` = plan
    from the latest research."""
    body = (body or "").strip()
    if not body:
        run_news_scan(token, send, chat_id)
        return
    if body.startswith("http://") or body.startswith("https://"):
        run_news_plan(token, send, chat_id, url=body)
        return
    send("sendMessage", {"chat_id": chat_id,
        "text": "News agent:\n• /news  — scan all business feeds now\n"
                "• /news <article-link>  — build a business plan + DOCX from that news\n"
                "• /newsplan  — business plan + DOCX from your latest /research\n"
                "Paste a direct publisher link (not a Google News wrapper) for full text.",
        "reply_markup": news_menu(), "disable_web_page_preview": "true"})

# ----------------------------------------------------------------- update loop

def safe_callback_answer(send, callback_id, **extra):
    if not callback_id:
        return
    try:
        send('answerCallbackQuery', {'callback_query_id': callback_id, **extra})
    except HTTPError as exc:
        if exc.code != 400:
            raise
        # Scheduled GitHub polling often receives callbacks after Telegram expiry.

def process_update(update, *, send, allowed_ids, database, ideas,
                   token=None, repository="", job_token=""):
    callback=update.get("callback_query")
    if isinstance(callback,dict):
        callback_id=callback.get("id")
        chat_id=(callback.get("message") or {}).get("chat",{}).get("id")
        if not allowed(chat_id,allowed_ids):
            if callback_id:
                safe_callback_answer(send,callback_id,text="Not authorized",show_alert="true")
            return "denied"
        # Stop the button spinner IMMEDIATELY, before any processing. The
        # GitHub Actions runner wakes on a 5-minute schedule, so without this
        # the spinner runs for up to ~30s and the menu feels frozen.
        if callback_id:
            safe_callback_answer(send,callback_id,text="⏳ Working…")
        data=callback.get("data","")
        if data=="bc:aimenu":
            text=("🤖 BizCrax AI — ask me ANYTHING about business opportunities, or tap a shortcut.\n"
                  "Example: /ai find a small capital food business in Malaysia")
            markup=ai_menu()
        elif data=="bc:research":
            text=("Research engine (V2): send /research <topic> [micro|small|medium|large]\n"
                  "Instant ack → discovery rounds → source verification → scored 360° summary → DOCX report.\n"
                  "Example: /research agrotech small")
            markup=research_help()
        elif data=="bc:study":
            text=agent_skill.state_text()
            markup=agent_skill.study_menu()
        elif data.startswith("bc:ai:"):
            key=data[6:]
            if key=="ask":
                text=("✍️ Ask the AI anything, e.g.:\n"
                      "/ai find a low cost food business in Kuala Lumpur\n"
                      "/ai high potential tech services small capital")
            else:
                topic=ai_shortcut(key)
                if not topic:
                    text="Unknown shortcut."
                else:
                    handle_ai_command(token,send,chat_id,topic)
                    return "sent"
            markup=ai_menu()
        elif data.startswith("bc:report:"):
            job=load_job(data[10:])
            if job and job.get("status")=="completed" and token:
                if deliver_report(token,chat_id,job):
                    return "sent"
            text=("Report for this job is not on this runner yet. Send /research with the same "
                  "topic to rebuild it, or tap the button again after the next scheduled run.")
            markup=research_help()
        elif data=="bc:news:scan":
            run_news_scan(token,send,chat_id)
            return "sent"
        elif data=="bc:news:plan":
            run_news_plan(token,send,chat_id)
            return "sent"
        elif data=="bc:news":
            text=("📰 News agent — reads business-development news and builds a business plan "
                  "(flow, budget, investment, M&A + joint venture, marketing, risk).\n"
                  "• Tap 'Scan latest' to read every feed now\n"
                  "• Tap 'Business plan from top research' to turn your last /research into a plan\n"
                  "• Or paste an article link (direct publisher URL, not a Google News wrapper) "
                  "and I will build a plan + DOCX from it")
            markup=news_menu()
        else:
            text,markup=handle_callback(data,database,ideas)
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
        # The callback was already answered at the top of the handler (fast ack);
        # a second answer is rejected by Telegram (400) so it is intentionally omitted.
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
    body=text.strip().partition(" ")[2].strip() if text.strip() else ""
    # A bare pasted article link (no command) → build a business plan from it.
    if token and text.strip().startswith(("http://","https://")):
        url=text.strip().split()[0]
        run_news_plan(token,send,chat_id,url=url)
        return "sent"
    if command in ("/research","/report") and token:
        handle_research_command(token,send,chat_id,body)
        return "sent"
    if command in ("/ai","/biz") and token:
        handle_ai_command(token,send,chat_id,body)
        return "sent"
    if command=="/aimenu" and token:
        handle_ai_command(token,send,chat_id,"")
        return "sent"
    if command in ("/study","/agent"):
        send("sendMessage",{"chat_id":chat_id,
            "text":agent_skill.state_text(),
            "reply_markup":agent_skill.study_menu(),
            "disable_web_page_preview":"true"})
        return "sent"
    if command=="/news" and token:
        handle_news_command(token,send,chat_id,body)
        return "sent"
    if command in ("/newsplan","/plan") and token:
        run_news_plan(token,send,chat_id)
        return "sent"
    if command in ("/sector","/sectors"):
        response="Select a business sector:"
        markup=sectors()
    else:
        response=search_text(text,database,ideas)
        markup=home()
    send("sendMessage",{"chat_id":chat_id,"text":response,
        "reply_markup":markup,"disable_web_page_preview":"true"})
    return "sent"

def poll_once(token,allowed_ids,database,ideas,telegram_api=api,max_updates=50,
             repository="",job_token=""):
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
            outcomes["suppressed"]=outcomes.get("suppressed",0)+1
        else:
            outcome=process_update(update,send=call,allowed_ids=allowed_ids,database=database,
                                   ideas=ideas,token=token,repository=repository,job_token=job_token)
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
    # Register the bottom-left ⋮ command menu (best effort, never fatal).
    try:
        api(token,"setMyCommands",{
            "commands":json.dumps([
                {"command":"start","description":"Open the main menu"},
                {"command":"ai","description":"AI bizcollector — ask anything (research + synthesis)"},
                {"command":"study","description":"🧠 Agent study — level, XP, domains, saved skills"},
                {"command":"research","description":"Research engine V2: topic [micro|small|medium|large]"},
                {"command":"news","description":"News agent: scan business feeds or /news <article-link> for a plan"},
                {"command":"newsplan","description":"Business plan + DOCX from your latest research"},
                {"command":"report","description":"Alias of /research with full DOCX report"},
                {"command":"search","description":"Search saved audited records"},
                {"command":"sector","description":"Browse by sector"},
                {"command":"help","description":"Instructions"}])})
        print("Telegram commands registered",flush=True)
    except (OSError, ValueError, RuntimeError) as exc:
        print("Command menu registration skipped:",type(exc).__name__,flush=True)
    repository=os.environ.get("GITHUB_REPOSITORY","")
    job_token=os.environ.get("GITHUB_TOKEN","")
    count=poll_once(token,allowed_ids,db,load_ideas(),repository=repository,job_token=job_token)
    print(f"Telegram updates processed: {count}")

if __name__=="__main__":
    main()
