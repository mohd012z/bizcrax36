import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import worker from '../worker/telegram.js';

function setup(){
 const calls=[];
 const original=globalThis.fetch;
 globalThis.fetch=async(url,opts)=>{calls.push({url,body:JSON.parse(opts.body)});return {ok:true,status:200};};
 const env={TELEGRAM_WEBHOOK_SECRET:'secret',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_ALLOWED_CHAT_IDS:'123'};
 const request=(text,secret='secret')=>new Request('https://example.com/telegram',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':secret},body:JSON.stringify({update_id:12,message:{chat:{id:123},text}})});
 return {calls,env,request,restore:()=>{globalThis.fetch=original;}};
}
test('rejects invalid webhook secret',async()=>{
 const x=setup();
 try{assert.equal((await worker.fetch(x.request('/status','wrong'),x.env)).status,403);assert.equal(x.calls.length,0);}
 finally{x.restore();}
});
test('status replies with queue-based processing',async()=>{
 const x=setup();
 try{assert.equal((await worker.fetch(x.request('/status'),x.env)).status,200);assert.match(x.calls[0].body.text,/queued for GitHub Actions/);}
 finally{x.restore();}
});
test('research without queue reports configuration error',async()=>{
 const x=setup();
 try{assert.equal((await worker.fetch(x.request('/research aviation'),x.env)).status,200);assert.match(x.calls[0].body.text,/not configured/);}
 finally{x.restore();}
});
