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
  if(data==="bc:help") return reply(env,chat,"Commands: /start /status /sector /research topic. Research runs separately on GitHub Actions.");
  if(data.startsWith("sector:")){
   const i=Number(data.slice(7));
   if(Number.isInteger(i)&&i>=0&&i<SECTORS.length) return reply(env,chat,"Research topic: "+SECTORS[i]+". Send /research "+SECTORS[i]+" Malaysia");
  }
  return reply(env,chat,"Use /research followed by a topic for fresh business discovery. Published research menus will be connected in the next release.");
 }
 const text=typeof msg.text==="string"?msg.text.trim():"";
 const cmd=commandText(text);
 if(cmd==="/start"||cmd==="/help") return reply(env,chat,"BizCrax36 is online. Send /research <topic> to request business research, or use the menu.");
 if(cmd==="/status") return reply(env,chat,"BizCrax36 webhook online. Research is handled by a separate scheduled workflow.");
 if(cmd==="/sector"||cmd==="/sectors") return reply(env,chat,"Select a business sector:",SECTOR_MENU);
 if(cmd==="/research"){
  const query=text.slice(text.indexOf(" ")+1).trim();
  if(!text.includes(" ")||!query||query.length>120) return reply(env,chat,"Usage: /research aviation training Malaysia (1–120 characters).");
  if(!env.RESEARCH_QUEUE) return reply(env,chat,"Research queue is not configured. Request was not queued.");
  const requestId="tg-"+String(update.update_id);
  try{
   await env.RESEARCH_QUEUE.send({request_id:requestId,chat_id:chat,query,received_at:new Date().toISOString()});
  }catch(error){
   console.error("Queue enqueue failed",error.message);
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
