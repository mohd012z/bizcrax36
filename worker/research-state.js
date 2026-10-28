export async function readJob(db,id){return db.prepare('SELECT state FROM research_jobs WHERE request_id=?').bind(id).first();}
export async function markDispatched(db,id){return db.prepare('UPDATE research_jobs SET state=? WHERE request_id=? AND state=?').bind('DISPATCHED',id,'QUEUED').run();}
export function shouldDispatch(row){return row?.state==='QUEUED';}
