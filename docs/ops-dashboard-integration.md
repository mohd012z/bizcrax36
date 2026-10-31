# Operations dashboard integration — isolated candidate

This branch is based on PR #15 commit c660cc5281b3af6a07a7b3a96b758cebcd07af32.
It does not change Telegram polling, webhook settings, production configuration or the existing opportunity API.

## Current status
- The separately generated mobile HTML, reference Python API, PWA shell and tests remain in the downloadable candidate ZIP; they have **not** been copied to this branch.
- Existing backend/search_api.py reads SQLite records; backend/orchestrator.py is a deterministic planning workflow. Neither exposes the proposed PostgreSQL ops_jobs schema.
- A read-only adapter and real backend schema mapping are prerequisites to live queue metrics.
- The reference API has unresolved authentication, CSRF, rate-limiting, worker-health and Vercel runtime gaps. Do not deploy it as-is.
- Recovery actions must remain disabled until transaction-level integration tests pass.

## Integration gates
1. Inventory actual queue persistence and hosting runtime.
2. Define authenticated read-only snapshot contract with no secrets sent to browsers.
3. Write additive migrations, restricted PostgreSQL role and RLS tests.
4. Implement read-only adapter and test missing/empty/invalid data.
5. Test lease fencing, idempotency and delivery uncertainty before enabling writes.
6. Validate responsive layout, offline mode and PWA installation on Android.
7. Execute existing repository regressions and live smoke tests in an authorized staging environment.
8. Keep PR #15 draft; no merge, webhook change, billing change or production deployment.

## Local candidate
The generated ZIP was supplied in the ChatGPT conversation, not committed to this repository. Do not represent this branch as a completed integration.
