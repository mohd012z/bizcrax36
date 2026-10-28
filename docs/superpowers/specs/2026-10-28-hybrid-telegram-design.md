# Hybrid Telegram runtime

Build on the user's previously selected A+B arrangement: persistent local
Telegram listeners plus bounded GitHub Actions execution. No new monthly host,
paid API, or runner plan is enabled. The existing three repair PRs remain draft
until activation and live bot replies are verified.

## Approaches

- Selected A+B: existing Linux/Android-capable persistent listener, local durable
  queue, GitHub background jobs. Matches the latest approved approach and uses
  the existing Python/Node engines. Requires an available persistent host.
- Existing Cloudflare V3 branch: webhook + D1 + Queue + GitHub. This is an
  alternative deployment, not a simultaneous second consumer. Its old dispatch
  contract does not match main and its cloud resources were not verified.
- Actions-only: scheduled polling remains an explicit fallback when no listener
  is running; it cannot guarantee immediate replies.

## Responsibilities

BizCollector's listener handles menus/status, persists heavy commands in SQLite,
then acknowledges them. A separate thread dispatches jobs, so it never runs
research on the polling path. All heavy command/button routing is preserved by
executing the existing process_update handler in a matching workflow. Only authenticated encrypted minimal update fields needed by that handler
cross the dispatch boundary; plaintext chat IDs and commands stay out of inputs.

The cloud workflow validates the same chat allowlist, validates the request ID,
serializes duplicate request IDs, checks prior successful runs, executes the
existing research engine, sends results and available DOCX files through the
existing Telegram secret, and uses the existing research-history persistence
mechanism. No bot token is sent in workflow inputs; no raw updates are published.

msasoup keeps interactive sessions on its persistent listener and its scheduled
book deliveries on Actions. Helix keeps continuous callbacks on its listener and
market snapshots/scheduled processing on Actions. News_ifxhelper retains its
canonical sender and deduplication; no second signal producer is added.

## Reliability and limits

Queue records survive restarts; enqueue precedes acknowledgement. Dispatch uses
leases, retries with backoff, a rolling 24-hour cap, and a per-chat pending cap.
Timeouts can cause duplicate dispatches; workflow serialization and a prior-
success check suppress completed duplicates. A crash after a Telegram send and
before successful completion can replay a response: exactly-once delivery is
not claimed. Exhausted retries remain visible, never a silent local fallback.

Activation requires matching workflow code on the configured approved ref,
Actions-write dispatch credentials scoped to this repository, existing Telegram
secrets in Actions, and one owner of getUpdates. Neither migration nor a failure
may automatically delete a webhook or start a second poller. Cloud unavailability
does not block lightweight listener commands. Quota exhaustion is explicit.
