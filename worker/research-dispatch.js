/**
 * Cloudflare Queue consumer. Dispatches research to GitHub Actions.
 * Requires GITHUB_DISPATCH_TOKEN (fine-grained Actions write for this repo).
 * Queue retries transient errors. A GitHub dispatch is not idempotent:
 * duplicate research runs are possible if the dispatch succeeds but ack fails.
 */
export default {
 async queue(batch,env){
  if(!env.GITHUB_DISPATCH_TOKEN) throw new Error("Missing GitHub dispatch credential");
  for(const message of batch.messages){
   const job=message.body;
   if(!job||!/^tg-\\d+$/.test(String(job.request_id))||!Number.isSafeInteger(Number(job.chat_id))||typeof job.query!=="string"||job.query.length>120){
    console.error("Discarding invalid research job");message.ack();continue;
   }
   const response=await fetch("https://api.github.com/repos/mohd012z/bizcrax36/actions/workflows/agentic-research.yml/dispatches",{
    method:"POST",
    headers:{"Authorization":"Bearer "+env.GITHUB_DISPATCH_TOKEN,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"bizcrax36-queue"},
    body:JSON.stringify({ref:"main",inputs:{query:job.query,country:"Malaysia",chat_id:String(job.chat_id),request_id:job.request_id}})
   });
   if(response.status===204){message.ack();continue;}
   const detail=await response.text();
   console.error("Research dispatch failed HTTP "+response.status+" "+detail.slice(0,200));
   message.retry({delaySeconds:response.status===429?120:30});
  }
 }
};
