# Run BizCrax36 business-project research and blueprint

This workflow produces a structured, auditable **draft**, not an independently verified business plan.

## Local commands (Python 3.11+, no paid API)
```bash
python -m unittest discover -s tests -v
python -m compileall -q backend tests
python -m backend.business_blueprint examples/sme-ocr-business.json --output data/sme-ocr-blueprint.json
python -m backend.search_api --database data/research.sqlite3
```
The search API listens on http://127.0.0.1:8765/api/opportunities by default. It does not create verified opportunities. It is local-only; do not expose it publicly without authentication, TLS, rate limiting and deployment review.

## Evidence collection checklist for every project
Record the exact claim, original source URL, retrieved date/time, issuing organization, document ID, quote/page, jurisdiction, whether a customer/supplier confirmed it, limitations and change history. For customer interviews collect consent and avoid storing unnecessary personal data. Keep quotations and customer discussions separate from government tenders. Do not automatically promote source metadata to verified facts.

## Business operating playbook
1. Define target buyer, problem, service boundary and alternatives.
2. Interview at least 3 prospective customers, documenting specific needs and willingness to pay.
3. Collect at least 2 independent supplier quotations where suppliers are involved.
4. Confirm relevant registrations, permits, privacy and tax obligations before commercial operation. For Malaysia see https://malaysiabiz.gov.my/en and https://www.ssm.com.my/Pages/Services/Registration-of-Business-%28ROB%29/EzBiz-Online.aspx. Registration is not a substitute for sector-specific permits.
5. Design a small pilot with scope, acceptance criteria, pricing, delivery steps and cancellation terms.
6. Calculate startup cost, per-sale variable cost, fixed cost, sales volume, contribution, break-even and cash gap; run downside/base/upside sensitivity.
7. Select outreach channels, prospect qualification, proposal and follow-up cadence; measure conversion and acquisition cost.
8. Assign owners for procurement, delivery, quality assurance, invoicing, customer support and risk controls.
9. Review pilot evidence and decide to scale, revise or stop. Do not call a business launch-ready based solely on a generated report.

## Data readiness rules
- `evidence_count` counts structurally complete metadata, **not authenticated facts**.
- `financial_model.status=scenario_only` indicates math on user-provided assumptions, **not a validated forecast**.
- `ready_to_launch` remains false until independent legal, commercial, and execution checks are implemented.
- Separate evergreen business ideas from time-limited issuer-verified tenders.
- No unattended crawler or live third-party data verification is configured by this blueprint.

## Next build gates
1. Implement input schema validation, richer provenance and independent source verification.
2. Add per-sector operating checklists, financial sensitivity analysis, report rendering and exports.
3. Add a persistent authenticated research API, queue, scheduler and UI.
4. Run tests in CI, verify against issuer sources and pilot with real consenting customers.
