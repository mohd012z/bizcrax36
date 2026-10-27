/**
 * Stateless Telegram webhook: fast replies without a permanent server.
 * Required Cloudflare secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET,
 * TELEGRAM_ALLOWED_CHAT_IDS. Set webhook separately only after deployment.
 */
const MENU = {inline_keyboard:[
 [{text:"🔎 Search opportunities",callback_data:"bc:search"},{text:"💡 Business ideas",callback_data:"bc:ideas"}],
 [{text:"📋 All research",callback_data:"bc:all"},{text:"✅ Verified live",callback_data:"bc:live"}],
 [{text:"🏷 Sector ▾",callback_data:"bc:sectors"},{text:"🔍 Review required",callback_data:"bc:review"}],
 [{text:"ℹ️ Help",callback_data:"bc:help"}]
]};
export const BOT_COMMANDS=[
 {command:"start",description:"Open BizCrax36 menu"},
 {command:"research",description:"Research a business opportunity"},
 {command:"status",description:"Check bot status"},
 {command:"sector",description:"Browse business sectors"},
 {command:"help",description:"Commands and instructions"}
];
export async function registerBotCommands(env){
 if(!env.TELEGRAM_BOT_TOKEN) throw new Error("Missing Telegram bot token");
 const response=await fetch("https://api.telegram.org/bot"+env.TELEGRAM_BOT_TOKEN+"/setMyCommands",{
  method:"POST",headers:{"content-type":"application/json"},
  body:JSON.stringify({commands:BOT_COMMANDS,scope:{type:"default"}})
 });
 if(!response.ok) throw new Error("Telegram command registration failed: HTTP "+response.status);
 return true;
}
const SECTORS=["Digital","Energy","Aerospace","Manufacturing","Tourism","Agriculture"];
const SECTOR_MENU={inline_keyboard:SECTORS.map((x,i)=>[{text:x,callback_data:"sector:"+i}]).concat([[{text:"⬅ Back",callback_data:"bc:home"}]])};
function allowed(id,env){return String(env.TELEGRAM_ALLOWED_CHAT_IDS||"").split(",").map(x=>x.trim()).includes(String(id))}
async function telegram(env,method,payload){
 const response=await fetch("https://api.telegram.org/bot"+env.TELEGRAM_BOT_TOKEN+"/"+method,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});
 if(!response.ok) throw new Error("Telegram "+method+" HTTP "+response.status);
}
async function reply(env,chat,text,markup=MENU){
 await telegram(env,"sendMessage",{chat_id:chat,text,reply_markup:markup,disable_web_page_preview:true});
}
function commandText(text){
 const token=text.trim().split(/\s+/,1)[0].split("@")[0].toLowerCase();
 return token;
}
async function handle(update,env){
 const callback=update.callback_query;
 const msg=callback?.message||update.message;
 const chat=msg?.chat?.id;
 if(chat===undefined || !allowed(chat,env)) return;
 if(callback){
  // Answer quickly; never let an expired callback block other messages.
  try{await telegram(env,"answerCallbackQuery",{callback_query_id:callback.id})}catch(_){}
  const data=callback.data||"";
  if(data==="bc:sectors") return reply(env,chat,"Select business sector:",SECTOR_MENU);
  if(data==="bc:home") return reply(env,chat,"BizCrax36 — choose an option:");
  if(data==="bc:search") return reply(env,chat,"Send /research followed by your topic, for example /research aviation training Malaysia");
  if(["bc:ideas","bc:all","bc:live","bc:review"].includes(data)){
   if(!env.DB) return reply(env,chat,"Research history is unavailable until the database is configured.");
   const state=data==="bc:live"?"COMPLETE":data==="bc:review"?"QUEUED":null;
   const sql=state
    ?"SELECT request_id,query,state FROM research_jobs WHERE chat_id=? AND state=? ORDER BY created_at DESC LIMIT 8"
    :"SELECT request_id,query,state FROM research_jobs WHERE chat_id=? ORDER BY created_at DESC LIMIT 8";
   const stmt=env.DB.prepare(sql);
   const rows=await (state?stmt.bind(String(chat),state):stmt.bind(String(chat))).all();
   const jobs=rows.results||[];
   if(!jobs.length) return reply(env,chat,"No matching research requests found. Send /research followed by a topic.");
   return reply(env,chat,"Recent research requests:\\n"+jobs.map(j=>j.request_id+" · "+j.state+" · "+j.query).join("\\n"));
  }
  if(data==="bc:help") return reply(env,chat,"Commands: /start /status /sector /research topic. Research is queued for GitHub Actions processing.");
  if(data.startsWith("sector:")){
   const i=Number(data.slice(7));
   if(Number.isInteger(i)&&i>=0&&i<SECTORS.length) return reply(env,chat,"Research topic: "+SECTORS[i]+". Send /research "+SECTORS[i]+" Malaysia");
  }
  return reply(env,chat,"Use /research followed by a topic for fresh business discovery. Published research menus will be connected in the next release.");
 }
 const text=typeof msg.text==="string"?msg.text.trim():"";
 const cmd=commandText(text);
 if(cmd==="/start"||cmd==="/help") return reply(env,chat,"BizCrax36 is online. Send /research <topic> to request business research, or use the menu.");
 if(cmd==="/status") return reply(env,chat,"BizCrax36 webhook online. Research requests are queued for GitHub Actions processing.");
 if(cmd==="/sector"||cmd==="/sectors") return reply(env,chat,"Select a business sector:",SECTOR_MENU);
 if(cmd==="/research"){
  const query=text.slice(text.indexOf(" ")+1).trim();
  if(!text.includes(" ")||!query||query.length>120) return reply(env,chat,"Usage: /research aviation training Malaysia (1–120 characters).");
  if(!env.RESEARCH_QUEUE || !env.DB) return reply(env,chat,"Research storage or queue is not configured. Request was not queued.");
  const requestId="tg-"+String(update.update_id);
  try{
   const inserted=await env.DB.prepare("INSERT OR IGNORE INTO research_jobs (request_id,update_id,chat_id,query,state) VALUES (?,?,?,?,?)").bind(requestId,update.update_id,String(chat),query,"QUEUED").run();
   if(inserted.meta?.changes===0) {
    const previous=await env.DB.prepare("SELECT state FROM research_jobs WHERE request_id=?").bind(requestId).first();
    if(previous?.state!=="FAILED") return reply(env,chat,"Request already received: "+requestId);
    await env.DB.prepare("UPDATE research_jobs SET state=? WHERE request_id=?").bind("QUEUED",requestId).run();
   }
   await env.RESEARCH_QUEUE.send({request_id:requestId,chat_id:chat,query,received_at:new Date().toISOString()});
  }catch(error){
   try { await env.DB.prepare("UPDATE research_jobs SET state=? WHERE request_id=?").bind("FAILED",requestId).run(); }catch(_){}
   console.error("Research request persistence or enqueue failed",error.message);
   return reply(env,chat,"Research queue unavailable. Request was not queued; please retry later.");
  }
  return reply(env,chat,"Research queued: "+query+"\\nRequest ID: "+requestId+"\\nAwaiting research processing.");
 }
 return reply(env,chat,"Unknown command. Send /help.");
}
export default {
 async fetch(request,env,ctx){
  const url=new URL(request.url);
  if(url.pathname!=="/telegram"||request.method!=="POST") return new Response("Not found",{status:404});
  const secret=request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if(!env.TELEGRAM_WEBHOOK_SECRET||!env.TELEGRAM_BOT_TOKEN||!env.TELEGRAM_ALLOWED_CHAT_IDS||secret!==env.TELEGRAM_WEBHOOK_SECRET) return new Response("Unauthorized",{status:403});
  let update;
  try{update=await request.json()}catch(_){return new Response("Invalid JSON",{status:400})}
  if(!update||typeof update!=="object") return new Response("Invalid update",{status:400});
  try { await handle(update,env); return new Response("OK"); }
  catch(e) { console.error("Telegram processing failed:",e.message); return new Response("Retry", {status:503}); }
 }
};
