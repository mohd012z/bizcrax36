# BizCrax36 — Agentic Research V2

Evidence-first research engine: free-text topic → discovery rounds → source
verification → weighted 0–100 scoring → 360° dossier → DOCX report with charts.
Stdlib only. No paid API, no LLM in the core path.

## Flow (matches the corrected architecture diagram)

```
/research <topic> [micro|small|medium|large]
      │  instant ack (fast response guaranteed)
      ▼
queued → researching → verifying → scoring → completed   (staged, auditable)
      │
      ├─ Round 1: demand discovery (market demand, SME suppliers,
      │            government programmes, procurement, capital-band query)
      ├─ Round 2: gap queries (competition/pricing, licence/registration,
      │            customer-demand evidence)  ← the feedback loop
      ├─ Verify: fetch top source pages; ≥60% of headline words present
      │            = source-verified (retrieved page ≠ demand proof)
      ├─ Score: weighted 0–100, every metric labeled evidence|assumed
      └─ 360° dossier (14 sections, each VERIFIED/ESTIMATED/ASSUMED/UNAVAILABLE)
             → Telegram summary + 📄 Report (DOCX) button
```

## Commands

| Command | What it does |
|---|---|
| `/research <topic> [band]` | Full V2 pipeline: ack → summary → DOCX report button |
| `/report <topic> [band]` | Alias of `/research` |
| `/ai <anything>` | **AI bizcollector** (Minda, same method as AI_msa): free text → AI intent parsing (topic + capital band) → full V2 research → AI synthesis with FACT/INFER/ASSUME labels. Fail-open: without Minda the deterministic engine still answers. |
| `/aimenu` | AI menu: shortcuts (high potential / low cost / small / medium / large) + ask box |
| 🤖 AI bizcollector button | Home-menu shortcut to the AI menu |
| 📄 Report button | Delivers the stored DOCX (jobs persisted to `data/research-jobs/`) |
| 🚀 Research engine button | Shows V2 usage |

Capital bands: `micro` (RM0–10k), `small` (10k–250k), `medium` (250k–2M),
`large` (2M+). Bands shape queries and the capital-accessibility metric.

## Files

- `backend/research_v2.py` — plan, 2-round parallel discovery, verify, score
- `backend/research_queue.py` — staged job runner, dedup window, diagnostics
- `backend/dossier.py` — 14-section dossier + Telegram summary text
- `backend/reports.py` — PNG charts (pure stdlib) + strict-OOXML DOCX
- `backend/telegram_poll_once.py` — fast-ack flow, job store, DOCX delivery
- `backend/telegram_menu.py` — research + report buttons
- `.github/workflows/research-v2.yml` — manual deep research + artifact
- `tests/test_research_v2.py`, `test_dossier_queue.py`, `test_reports.py`

## Durable jobs across ephemeral runners

GitHub runners are stateless. After a research job completes, the workflow
commits `data/research-jobs/<id>/` (job.json + report.docx + charts) and pushes
to `main` using the workflow's `GITHUB_TOKEN` (requires `contents: write`).
A later runner — which freshly checks out `main` — can therefore answer
`bc:report:<id>` taps for jobs run minutes earlier. Persistence is fail-open:
if the push fails, the summary was already delivered and the same `/research`
rerun rebuilds the report (15-minute dedup window suppresses re-discovery of
identical completed jobs).

## Scoring (preliminary, not a profitability claim)

Weights: demand 25, unit_economics 15, competition 15,
capital_accessibility 15, operational_feasibility 15, regulatory_readiness 15.
Each metric carries `basis: evidence|assumed` and a `note`. Headline term
matches, verified-source count and freshness feed the demand metric; round-2
gap hits feed competition and regulatory; capital band feeds accessibility.
All leads stay `review_required`.

## Verification limits (stated honestly)

- Google News RSS links are `news.google.com/rss/articles/...` wrappers;
  server-side fetches cannot resolve the publisher URL, so live
  source-verification rate is low by construction. Verification works fully
  for direct publisher links (e.g. TED collector records, manual records).
  The engine labels this per-candidate; it never inflates unverified leads.
- `when=30d` freshness filter is applied to discovery by default.

## Local run

```bash
python -m unittest discover -s tests -v
python - <<'PY'
from backend.research_queue import run_job
from backend.dossier import build as build_dossier
from backend.reports import generate_report
job, result, dossier = run_job("energy efficiency services", capital="small")
print(generate_report(dossier, result, "out/"))
PY
```

## Web (360° Command Center) + APK backup

- `python -m backend.web_api --host 127.0.0.1 --port 8765`
  serves `web/index.html` (the Command Center) plus the API:
  `/api/research?topic=&capital=&country=` (same V2 engine, persisted jobs),
  `/api/jobs`, `/api/job/<id>`, `/api/job/<id>/report` (DOCX),
  `/api/job/<id>/chart/<name>` (PNG). Optional `WEB_API_TOKEN` env adds an
  `X-BizCrax-Token` header requirement on `/api/research`.
- **APK** (`android/`): a WebView shell that renders the same `web/index.html`
  from app assets and proxies `/api/*` to the configured backend host
  (⚙️ button in the UI sets the base URL). Emulator default `http://10.0.2.2:8765`;
  on a phone use the machine's LAN IP with `web_api --host 0.0.0.0`.
  Build: `cd android && ./gradlew assembleDebug` (AGP 8.5.2, Kotlin 1.9.24,
  minSdk 26). CI: `.github/workflows/apk.yml` uploads the APK as an artifact.
- The UI is a single file with zero external dependencies (offline-capable),
  so the HTML, browser and APK always render identical output for the same
  API response.
