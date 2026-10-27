import test from "node:test";
import assert from "node:assert/strict";
import worker from "../worker/telegram-webhook.mjs";

const env={TELEGRAM_BOT_TOKEN:"test-token",TELEGRAM_WEBHOOK_SECRET:"secret",TELEGRAM_ALLOWED_CHAT_IDS:"123"};
const events=[];
const context={waitUntil(p){events.push(p);}};
function request(update,secret="secret"){
 return new Request("https://example.workers.dev/telegram",{method:"POST",headers:{"content-type":"application/json","X-Telegram-Bot-Api-Secret-Token":secret},body:JSON.stringify(update)});
}
test("rejects unauthenticated webhook",async()=>{
 assert.equal((await worker.fetch(request({update_id:1},"wrong"),env,context)).status,403);
});
test("health is available",async()=>{
 assert.equal((await worker.fetch(new Request("https://example.workers.dev/health"),env,context)).status,200);
});
test("automatically responds to /status",async()=>{
 const old=globalThis.fetch;const sent=[];
 globalThis.fetch=async(url,opts)=>{sent.push({url:String(url),body:JSON.parse(opts.body)});return new Response(JSON.stringify({ok:true,result:{}}),{status:200});};
 try{
  const response=await worker.fetch(request({update_id:2,message:{chat:{id:123},text:"/status"}}),env,context);
  assert.equal(response.status,200);
  await Promise.all(events.splice(0));
  assert.equal(sent.length,1);
  assert.match(sent[0].body.text,/webhook responder active/);
 }finally{globalThis.fetch=old;}
});
test("unauthorized chat receives no reply",async()=>{
 const old=globalThis.fetch;let count=0;
 globalThis.fetch=async()=>{count++;return new Response('{"ok":true,"result":{}}');};
 try{
  await worker.fetch(request({update_id:3,message:{chat:{id:999},text:"/status"}}),env,context);
  await Promise.all(events.splice(0));assert.equal(count,0);
 }finally{globalThis.fetch=old;}
});
