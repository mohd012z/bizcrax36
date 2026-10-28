# Telegram hybrid A+B

## What runs where

| Bot | Persistent listener | GitHub Actions |
| --- | --- | --- |
| BizCollector | Immediate menus/status, authorized durable queue, dispatch thread | Heavy research, AI commands, news scans/plans, report callbacks, scheduled delivery |
| msasoup | Interactive searches and private sessions, ordered per user | Existing daily licensed-book scouting and delivery |
| Helix | Continuous authorized BBMA callbacks | Existing market snapshots and scheduled processing |
| News_ifxhelper | Existing canonical transport unchanged | Existing news/reminder sender and deduplication |

The hybrid system has exactly one update consumer per bot. Outbound deliveries
can coexist with a listener. Two independent getUpdates pollers cannot be used
as a failover race. GitHub-only polling remains a deliberately selected fallback,
with its existing scheduler delays; it is never advertised as immediate.

## BizCollector request flow

1. Listener authorizes the chat and classifies the command/button.
2. Heavy work is saved in a private SQLite outbox before the acknowledgement.
3. A background thread encrypts the minimal update and dispatches the exact
   `request_id` + `update_encrypted` workflow contract. Menus remain on the
   listener thread; no research or AI completion runs there.
4. The cloud job decrypts using the existing Telegram secret, validates the
   allowlist and identity again, serializes duplicate request IDs, and checks
   recent successful runs before executing the existing engine.
5. The existing engine delivers results; newly generated research DOCX files
   are also sent directly. Existing research-history persistence is invoked only
   on approved main code, never by pushing a feature branch into main.
6. `/hybrid` reports the private queue's QUEUED, DISPATCHING, DISPATCHED and
   FAILED counts for the requesting chat. DISPATCHED means accepted by GitHub;
   it is not a claim that the research succeeded or completed.

Supported background messages are `/research`, `/report`, `/ai <topic>`,
`/biz <topic>`, `/news`, `/newsplan`, `/plan`, and direct article links. AI
shortcut, news scan/plan and report buttons use the same path. `/start`,
`/help`, `/status`, `/sector` and the AI menu remain local.

## Enable on the already approved persistent host

The source repair must first be reviewed and the matching cloud workflow made
available on the configured approved ref. Do not activate a client that targets
an absent or mismatched workflow. Install `requirements-hybrid.txt` into the
listener's virtual environment. Hybrid encryption uses pinned cryptography;
the default non-hybrid listener remains usable without it.

The listener's private `/etc/telegram-bots/bizcrax36.env` needs its existing
Telegram token/allowlist plus `GITHUB_DISPATCH_TOKEN`, a fine-grained token
restricted to Actions write for this repository. Do not put this token in
workflow inputs, git, or Telegram messages. GitHub Actions uses its existing
Telegram token/allowlist secrets and built-in GITHUB_TOKEN. No new AI provider
key is needed; the default workflow does not enable an LLM API.

Install `deploy/telegram-bizcollector-hybrid.conf` as
`/etc/systemd/system/telegram-bizcollector.service.d/hybrid.conf`. It selects
GitHub execution, approved main, persistent queue storage, 20 submissions per
rolling 24 hours and 3 pending local requests per chat. The host must also have
the original service from the runtime repair installed. No new hosting account
or paid billing plan is provisioned by these files.

Set the repository variable `TELEGRAM_RUNTIME=persistent`, wait for any in-flight
Actions polling job to finish, then activate/restart the single host service.
Retain a backup of the host database/outbox. No webhook is deleted by startup.
The service refuses a conflicting active webhook and stops on a 409 conflict.

On Android, the same Python module can run on an existing supervised Termux
host with the same environment. Android background killing and connectivity
still require actual device validation; a phone is not assumed to be 24/7.

## Failure behavior and privacy

The local queue survives restarts and leases interrupted dispatches. Dispatch
failures retry with backoff and stop after five attempts; failed records stay
visible. Limits remain in the database across restarts. These are submission
limits, not a replacement for GitHub's account-level spending controls. No
spending limit or paid runner is enabled or raised.

Minimal updates omit sender names and unrelated metadata. Dispatch envelopes
use authenticated Fernet encryption derived from the existing bot secret with
a versioned context; ciphertext expires after 24 hours. Chat IDs and commands
are not plaintext workflow inputs. Research outputs use the repository's
existing report/history flow; raw Telegram updates are never archived there.

Delivery is at least once around external side effects. A crash after sending a
Telegram reply but before a successful workflow completion can replay a reply.
A successful receipt is checked among the latest 100 workflow dispatch runs;
this is bounded duplicate suppression, not an unlimited exactly-once ledger.
GitHub dispatch rejection is not hidden by silently running expensive work in
the listener. Existing cloud failures remain visible in Actions/Telegram.

## Live acceptance and rollback

Before claiming the bot is live, verify an authorized background request starts
one cloud job, a menu/status reply still arrives during that job, a DOCX arrives,
unauthorized requests are rejected, duplicates are suppressed, the outbox
survives a restart, and a network outage recovers within the retry budget.
Confirm one consumer and the correct bot identity throughout.

To disable offloading, remove the hybrid service drop-in (or select
`HYBRID_EXECUTION=local`) and restart the one listener. This returns to existing
synchronous engine behavior; queued records are retained for deliberate
recovery. Stop the persistent service before selecting Actions polling again.
The source PR remains draft until host activation and these live gates pass.

## Source verification

Full local regression suite: **242 passed, zero failures**. Source compilation,
workflow/dispatch contract validation (where changed) and diff checks passed.
The live host, actual dispatch credentials, Telegram replies and deployment
cutover have not been verified. These counts do not claim production activation.
