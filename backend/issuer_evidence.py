"""Conservative issuer verification: explicit structured evidence, never page keyword guesses.

Use a trusted issuer-specific adapter to produce the evidence JSON. A generic HTML
page or a matching title/reference can NEVER confirm an open tender.
"""
from datetime import datetime,timezone
from backend.opportunity_filter import parse_deadline, status

TRUSTED_ADAPTERS={"issuer_structured_notice_v1"}
def verify_issuer_notice(candidate,evidence,now=None):
    now=now or datetime.now(timezone.utc)
    result=dict(candidate)
    result.update(checked_at=now.isoformat(),verification_status="unverified",
                  issuer_status="unknown",last_verified_at=None,
                  verification_reason="structured issuer evidence missing or incomplete")
    if not isinstance(evidence,dict) or evidence.get("adapter") not in TRUSTED_ADAPTERS:
        return result
    required=("issuer_url","reference","title","status","closing_at","retrieved_at","evidence_sha256")
    if any(not evidence.get(k) for k in required):
        return result
    if evidence["issuer_url"]!=candidate.get("source_url"):
        result["verification_reason"]="issuer URL mismatch"
        return result
    if str(evidence["reference"]).strip()!=str(candidate.get("reference","")).strip():
        result["verification_reason"]="reference mismatch"
        return result
    if " ".join(str(evidence["title"]).casefold().split())!=" ".join(str(candidate.get("title","")).casefold().split()):
        result["verification_reason"]="title mismatch"
        return result
    deadline=parse_deadline(evidence["closing_at"],candidate.get("timezone","UTC"))
    candidate_deadline=parse_deadline(candidate.get("closing_at"),candidate.get("timezone","UTC"))
    retrieved=parse_deadline(evidence["retrieved_at"],"UTC")
    if not deadline or not candidate_deadline or deadline!=candidate_deadline or not retrieved or retrieved>now:
        result["verification_reason"]="invalid or inconsistent dates"
        return result
    if (now-retrieved).total_seconds()>24*3600:
        result["verification_reason"]="issuer evidence stale"
        return result
    if evidence["status"] not in ("open","closed","cancelled"):
        result["verification_reason"]="issuer status not explicit"
        return result
    result.update(verification_status="issuer_verified",issuer_status=evidence["status"],
                  last_verified_at=retrieved.isoformat(),source_sha256=evidence["evidence_sha256"],
                  verification_reason="structured issuer status evidence")
    result["display_status"]=status(result,now)
    return result
