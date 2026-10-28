// Cloudflare Worker: event-driven Telegram replies. No GitHub cron required.
// Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, TELEGRAM_ALLOWED_CHAT_IDS.
// Optional KV binding UPDATES for cross-request duplicate suppression.
const SECTORS = ["All","Technology","Industrial","Energy","Aviation","Services"];
const menu = () => ({inline_keyboard:[
  [{text:"🔎 Search opportunities",callback_data:"bc:search"},{text:"💡 Business ideas",callback_data:"bc:mode:ideas"}],
  [{text:"📋 All research",callback_data:"bc:mode:all"},{text:"✅ Verified live",callback_data:"bc:mode:live"}],
  [{text:"🏷 Sector ▾",callback_data:"bc:sectors"},{text:"🔍 Review required",callback_data:"bc:mode:review"}],
  [{text:"ℹ️ Help",callback_data:"bc:help"}]
]});
const sectorMenu = () => ({inline_keyboard:[...SECTORS.map((s,i)=>[{text:s,callback_data:"bc:sector:"+i}]),[{text:"◀ Back",callback_data:"bc:home"}]]});
const allowed = (id,env) => String(env.TELEGRAM_ALLOWED_CHAT_IDS||"").split(",").map(x=>x.trim()).includes(String(id));
async function telegram(env,method,payload){
  const res=await fetch("https://api.telegram.org/bot"+env.TELEGRAM_BOT_TOKEN+"/"+method,{
    method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});
  if(!res.ok) throw new Error("Telegram "+method+" HTTP "+res.status);
  const body=await res.json();
  if(!body.ok) throw new Error("Telegram "+method+" rejected");
  return body.result;
}
function safeText(s){return String(s||"").replace(/[<>]/g,"").slice(0,180);}
function decodeXml(s){return s.replace(/&amp;/g,"&").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g,"$1");}
function tag(xml,name){const m=xml.match(new RegExp("<"+name+"(?:\\s[^>]*)?>([\\s\\S]*?)<\\/"+name+">","i"));return m?decodeXml(m[1]).trim():"";}
async function research(query){
  const words=query.toLowerCase().match(/[a-z0-9]+/g)||[];
  const topic=words.filter(w=>w.length>2).slice(0,9).join(" ");
  const searches=[topic+" Malaysia market demand",topic+" Malaysia business suppliers",topic+" Malaysia government programme"];
  const found=new Map(), failures=[];
  for(const q of searches){
    try{
      const url="https://news.google.com/rss/search?"+new URLSearchParams({q,hl:"en-MY",gl:"MY",ceid:"MY:en"});
      const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),4500);
      let response;
      try{response=await fetch(url,{signal:controller.signal,headers:{"user-agent":"BizCrax36/1.0"}});}
      finally{clearTimeout(timeout);}
      if(!response.ok)throw new Error("RSS HTTP "+response.status);
      const xml=(await response.text()).slice(0,350000);
      for(const part of xml.match(/<item>[\s\S]*?<\/item>/g)||[]){
        const title=safeText(tag(part,"title"));const link=tag(part,"link");
        if(!title||!link.startsWith("https://"))continue;
        const key=title.toLowerCase().replace(/\s+/g," ");
        if(!found.has(key))found.set(key,{title,link});
        if(found.size>=15)break;
      }
    }catch(e){failures.push(q);}
  }
  const results=[...found.values()].slice(0,5);
  const lines=["Research: "+query,"Candidate news leads: "+found.size];
  for(let i=0;i<results.length;i++)lines.push((i+1)+". "+results[i].title+"\n"+results[i].link+"\nREVIEW_REQUIRED");
  if(!results.length)lines.push("No leads found; sources may be unavailable.");
  if(failures.length)lines.push("Source searches failed: "+failures.length);
  lines.push("Unverified news leads, not confirmed profitability, tenders or demand.");
  return lines.join("\n\n").slice(0,3900);
}
async function reply(update,env){
  const cb=update.callback_query, msg=cb?.message||update.message;
  if(!msg||!allowed(msg.chat?.id,env))return;
  const chat_id=msg.chat.id;
  if(cb){
    // Acknowledge button immediately; delivery still happens in this request's background task.
    try{await telegram(env,"answerCallbackQuery",{callback_query_id:cb.id});}catch(_){}
    const data=String(cb.data||"");
    let text="Choose an option:",reply_markup=menu();
    if(data==="bc:sectors"){text="Choose business sector:";reply_markup=sectorMenu();}
    else if(data==="bc:search")text="Send /research followed by a topic, e.g. /research aviation training Malaysia";
    else if(data==="bc:help")text="Commands: /start /status /sector /research topic. Research leads require verification.";
    else if(data.startsWith("bc:sector:")){
      const i=Number(data.slice(10));
      text=Number.isInteger(i)&&i>=0&&i<SECTORS.length?"Selected sector: "+SECTORS[i]+". Send /research "+SECTORS[i]+" Malaysia":"Invalid sector.";
    }else if(data.startsWith("bc:mode:"))text="To discover fresh opportunities send /research followed by your topic. Existing research remains in GitHub.";
    else if(data!=="bc:home")text="Menu expired. Select a new option.";
    try{
      if(Number.isInteger(msg.message_id))await telegram(env,"editMessageText",{chat_id,message_id:msg.message_id,text,reply_markup});
      else await telegram(env,"sendMessage",{chat_id,text,reply_markup});
    }catch(_){await telegram(env,"sendMessage",{chat_id,text,reply_markup});}
    return;
  }
  const raw=String(msg.text||"").trim();const command=(raw.split(/\s+/)[0]||"").split("@")[0].toLowerCase();
  let text="Send /start for menu or /research followed by a topic.",reply_markup=menu();
  if(command==="/start"||command==="/help")text="BizCrax36 automatic research bot. Send /research topic for fresh candidate discovery. Results are unverified leads.";
  else if(command==="/status")text="BizCrax36 webhook responder active. Research sources may be temporarily unavailable.";
  else if(command==="/sector"){text="Choose business sector:";reply_markup=sectorMenu();}
  else if(command==="/research"){
    const query=raw.slice(raw.indexOf(" ")+1).trim();
    if(!raw.includes(" ")||query.length<3||query.length>120)text="Usage: /research aviation training Malaysia (3–120 characters).";
    else text=await research(query);
  }
  await telegram(env,"sendMessage",{chat_id,text,reply_markup,link_preview_options:{is_disabled:true}});
}
export default {
  async fetch(request,env,ctx){
    const url=new URL(request.url);
    if(url.pathname==="/health")return new Response(JSON.stringify({status:"ok",service:"bizcrax36-webhook"}),{headers:{"content-type":"application/json"}});
    if(url.pathname!=="/telegram"||request.method!=="POST")return new Response("Not found",{status:404});
    if(!env.TELEGRAM_BOT_TOKEN||!env.TELEGRAM_WEBHOOK_SECRET||!env.TELEGRAM_ALLOWED_CHAT_IDS)return new Response("Not configured",{status:503});
    if(request.headers.get("X-Telegram-Bot-Api-Secret-Token")!==env.TELEGRAM_WEBHOOK_SECRET)return new Response("Unauthorized",{status:403});
    if(Number(request.headers.get("content-length")||0)>100000)return new Response("Too large",{status:413});
    let update;try{update=await request.json();}catch(_){return new Response("Invalid JSON",{status:400});}
    if(!Number.isInteger(update?.update_id))return new Response("Invalid update",{status:400});
    if(env.UPDATES){
      const key="telegram:"+update.update_id;
      if(await env.UPDATES.get(key))return new Response("ok");
      // KV is best-effort, not an atomic lock; duplicates are still possible under concurrency.
      await env.UPDATES.put(key,"1",{expirationTtl:86400});
    }
    ctx.waitUntil(reply(update,env).catch(e=>console.error("Telegram handler failed:",e.message)));
    return new Response("ok");
  }
};
