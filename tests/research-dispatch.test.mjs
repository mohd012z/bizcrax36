import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import consumer from '../worker/research-dispatch.js';

test('valid queued request is dispatched once and then skipped',async()=>{
 const states=new Map([['tg-123','QUEUED']]);
 let calls=0,acks=0;
 const db={prepare(sql){return {bind(...args){return {
  async first(){return {state:states.get(args[0])};},
  async run(){states.set(args[1],args[0]);return {success:true};}
 };}};}};
 const message={body:{request_id:'tg-123',chat_id:123,query:'aviation'},ack(){acks++},retry(){throw Error('unexpected retry')}};
 const original=globalThis.fetch;
 globalThis.fetch=async()=>{calls++;return {status:204};};
 try{
  const env={DB:db,GITHUB_DISPATCH_TOKEN:'test'};
  await consumer.queue({messages:[message]},env);
  await consumer.queue({messages:[message]},env);
  assert.equal(calls,1);
  assert.equal(acks,2);
  assert.equal(states.get('tg-123'),'DISPATCHED');
 }finally{globalThis.fetch=original;}
});
