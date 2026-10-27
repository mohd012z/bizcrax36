"""TED public API research adapter: published notices, NOT verified open tenders.

Uses only fixed official HTTPS endpoint; no arbitrary URL input or redirects.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import URLError

ENDPOINT="https://api.ted.europa.eu/v3/notices/search"
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("redirect refused")
def request_notices(query="publication-date >= 20261001",limit=20,opener=None):
    if not isinstance(query,str) or not 1<=len(query)<=500:
        raise ValueError("invalid expert query")
    if not isinstance(limit,int) or not 1<=limit<=100:
        raise ValueError("limit must be 1..100")
    payload=json.dumps({"query":query,"fields":["publication-number","notice-title",
        "publication-date"],"limit":limit,"page":1,"scope":"ALL"}).encode()
    req=Request(ENDPOINT,data=payload,headers={"Content-Type":"application/json",
        "Accept":"application/json","User-Agent":"BizCrax36-Research/0.2"},method="POST")
    opener=opener or build_opener(NoRedirect)
    with opener.open(req,timeout=20) as response:
        if response.geturl()!=ENDPOINT or response.headers.get_content_type()!="application/json":
            raise ValueError("unexpected source response")
        raw=response.read(2_000_001)
        if len(raw)>2_000_000:
            raise ValueError("response too large")
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get("notices"),list):
        raise ValueError("unexpected TED response shape")
    return data,hashlib.sha256(raw).hexdigest()
def normalize(data,digest,now=None):
    now=now or datetime.now(timezone.utc)
    records=[]
    for notice in data.get("notices",[]):
        if not isinstance(notice,dict):
            continue
        ref=notice.get("publication-number")
        if isinstance(ref,list):
            ref=ref[0] if ref else None
        if not isinstance(ref,str) or not ref or not all(c.isalnum() or c=="-" for c in ref):
            continue
        title=notice.get("notice-title")
        if isinstance(title,dict):
            title=next((v for v in title.values() if isinstance(v,str)),None)
        if isinstance(title,list):
            title=next((v for v in title if isinstance(v,str)),None)
        records.append({"title":title or "TED notice "+ref,"reference":ref,
          "issuer":"TED published notice","source_url":"https://ted.europa.eu/en/notice/"+ref,
          "country":"European Union","region":"Europe","type":"tender",
          "checked_at":now.isoformat(),"last_verified_at":None,
          "verification_status":"source_matched","issuer_status":"unknown",
          "closing_at":None,"source_sha256":digest,
          "verification_reason":"Official publication found; tender status and eligibility not confirmed"})
    return records
def run(output,query,limit):
    data,digest=request_notices(query,limit)
    rows=normalize(data,digest)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({"source":"TED","records":rows,"retrieved_at":datetime.now(timezone.utc).isoformat(),
        "live_confirmed":0},indent=2),encoding="utf-8")
    return rows
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=Path("data/ted-discovery.json"))
    p.add_argument("--query",default="publication-date >= 20261001")
    p.add_argument("--limit",type=int,default=20)
    a=p.parse_args()
    print("discovered=",len(run(a.output,a.query,a.limit))," verified_live=0")
