# Operations dashboard — isolated prototype

This branch contains a **static read-only shell**, not the complete previously generated candidate ZIP. The dashboard requests `/api/ops/snapshot` with same-origin credentials, uses bounded 60-second refresh when visible, and does not show fabricated live data. All recovery buttons remain disabled.

**Not deployed.** The endpoint is not implemented on this branch. The full candidate ZIP was generated separately in ChatGPT and was not uploaded to GitHub. Existing Telegram receiver and polling files are unchanged. Do not merge this branch as production-ready.

Before enabling operations: implement authenticated server-side snapshot, real queue mapping, least-privilege PostgreSQL access, CSRF protection, durable recovery actions, and CI/security/Android tests.
