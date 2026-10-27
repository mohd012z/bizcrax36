# BizCrax36 — diagram-to-production implementation map

## Current code
- `index.html`: mobile-friendly static opportunity shortlist and CSV export
- `backend/source_monitor.py`: public-page retrieval, timestamps, SHA-256, fail-closed errors
- `backend/opportunity_filter.py`: issuer-verified, fresh, unexpired opportunity search
- `backend/orchestrator.py`: 36-role workflow planner with explicit evidence gaps
- `tests/`: offline tests; `.github/workflows/tests.yml`: CI workflow

## Run locally
```bash
python -m unittest discover -s tests -v
python -m compileall -q backend tests
python -m backend.source_monitor --output data/source-monitor.json
python -m backend.orchestrator opportunity.json --output data/workflow-report.json
```
The monitor makes network requests. A retrieved page is NOT a verified tender. The orchestrator only plans 36 specialist analyses; it does not execute 36 AI models.

## Roadmap with acceptance gates
1. **Ingestion**: lawful official/private source adapters, rate limits, extraction schemas, full provenance, source availability metrics. Acceptance: sampled records match issuer pages.
2. **Storage and search**: PostgreSQL/SQLite, indexed search, expiry filtering at query time, audit history, source deduplication. Acceptance: expired/cancelled/stale records never appear as live.
3. **Scheduling**: external always-on worker, retries/backoff, timezone-aware deadlines, alerts. Acceptance: measured latency and alert delivery; no false real-time guarantees.
4. **36 specialist agents**: implement tools and evaluators for each defined role, bounded budgets and failure states. Acceptance: every claimed fact has evidence and each output has a trace.
5. **Financial and business design**: deterministic models for revenue, working capital, break-even and scenarios; marketing and operations templates. Acceptance: reconciled totals and disclosed assumptions.
6. **Reports and UX**: responsive dashboard, search, filters, citations, archive, charts, PDF/XLSX/DOCX exports, mobile QA. Acceptance: end-to-end test from verified notice to downloadable report.
7. **Security**: secret management, permissions, abuse limits, legal review and backup. Acceptance: security tests and recovery drill.

## Integrity
Never label simulated, inferred, undated, unverified or stale opportunities as live. Funding eligibility, company ownership and acquisition availability require independent verification. Keep draft PR unmerged until CI and live connector validation pass.
