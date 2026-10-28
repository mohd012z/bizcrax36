# Hybrid Telegram implementation plan

Goal: preserve immediate interactive replies while durable heavy jobs run in Actions.
Architecture: existing A+B listener, SQLite outbox, GitHub dispatch, existing engines.
Spec: docs/superpowers/specs/2026-10-28-hybrid-telegram-design.md

1. Add failing tests for heavy-command classification, minimal update payloads,
   durable enqueue, restart recovery, duplicate update IDs, quota limits, dispatch
   retry leases, and polling-path separation.
2. Implement backend/hybrid_queue.py and route eligible updates through an
   optional queue before existing synchronous handlers; leave defaults unchanged.
3. Add a dispatcher thread to the persistent runtime only in explicitly configured
   hybrid mode, with shutdown and configuration validation.
4. Add a matching hybrid-telegram-job.yml contract and backend/hybrid_cloud.py.
   Verify allowlists/request IDs and suppress completed duplicate runs before
   any Telegram action. Reuse existing handler, history, report delivery.
5. Document exact activation and rollback in all three repair branches. Keep
   scheduled deliveries and canonical signal ownership separate from polling.
6. Run full Python/Node regressions, compilation, workflow contract checks, and CI.
   Update draft PRs with source evidence and separate live activation gates.
