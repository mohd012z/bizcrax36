import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {shouldDispatch} from '../worker/research-state.js';

test('only queued jobs can be dispatched',()=>{
 assert.equal(shouldDispatch({state:'QUEUED'}),true);
 for(const state of ['DISPATCHED','COMPLETE','FAILED','RUNNING']){
  assert.equal(shouldDispatch({state}),false);
 }
 assert.equal(shouldDispatch(null),false);
});
