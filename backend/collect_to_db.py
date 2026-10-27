"""Persist official-source discoveries to the existing audit DB, without promoting to live."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from backend.ted_research import request_notices,normalize
from backend.discovery_pipeline import save

def collect(database,output,query="publication-date >= 20261001",limit=20,fetch=request_notices):
    data,digest=fetch(query,limit)
    records=normalize(data,digest)
    save(database,records)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({"retrieved_at":datetime.now(timezone.utc).isoformat(),
        "source":"TED","discovered":len(records),"verified_live":0,
        "records":records},indent=2,ensure_ascii=False),encoding="utf-8")
    return {"discovered":len(records),"verified_live":0}
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--database",type=Path,default=Path("data/research.sqlite3"))
    p.add_argument("--output",type=Path,default=Path("data/ted-discovery.json"))
    p.add_argument("--query",default="publication-date >= 20261001")
    p.add_argument("--limit",type=int,default=20)
    a=p.parse_args()
    print(json.dumps(collect(a.database,a.output,a.query,a.limit)))
