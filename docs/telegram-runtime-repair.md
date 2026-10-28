# Persistent Telegram listener repair

## Scope and current evidence

The source repair is tested locally. No persistent host, bot credentials, live
webhook registration, or live Telegram reply was available in this session.
Installing a service file does not prove the bot is online. GitHub Actions
success proves a job completed, not continuous listening.

## Cutover on an existing Linux host

Use the existing host, not this transient development workspace. Do not create
a paid service for this repair. Provision a `telegram-bots` service user, place
the tested checkout at `/opt/telegram-bots/bizcrax36`, and install its dependencies.
For Python repositories create `.venv`; for BizCrax36 the listener is stdlib-only.
Keep credentials in `/etc/telegram-bots/bizcrax36.env` (root-owned, mode 0600),
never in git or shell history. The service file has concrete paths and no
embedded credentials.

Set GitHub repository variable `TELEGRAM_RUNTIME=persistent` **before** starting
this service; let any in-flight `process-updates` job finish. That disables the
Actions consumer while leaving tests enabled. Required host environment:
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (or `TELEGRAM_ALLOWED_CHAT_IDS`).
No LLM/API key is required. `MAX_UPDATES` is 1..100 and `POLL_SECONDS` 0.1..30.
Optional existing `MINDA_*`/`LLM_PROXY_*` settings keep their existing behavior;
this repair creates no paid API account. Polling waits up to 25 seconds for
updates and confirms successful replies only. Data and reports persist under
`data/` and the service state directory. No GitHub token is needed for local
persistence. Optional repository pushes require a separate service override
permitting `.git` writes; do not enable them just to run the bot.

Research remains synchronous: an expensive research command can delay the next
command until it completes. This release repairs the listener lifecycle; it does
not claim durable background job isolation. A crash after sending and before
acknowledging can replay one response.


Stop every other consumer of this same bot token, including processes on
other hosts, before activation. Local locks cannot prevent cross-host conflicts.
Do not delete an existing webhook automatically. Confirm its owner and stop
it as part of an intentional cutover. Do not drop pending updates.

Copy `deploy/telegram-bizcollector.service` into `/etc/systemd/system/`, then run
`systemctl daemon-reload` and `systemctl enable --now telegram-bizcollector` on that host.
For BizCrax36, grant the service user ownership of the checkout's `data/`;
for msasoup grant ownership of `logs/`. systemd creates the private state
directory and restarts transient crashes. Configuration exit 78 stays stopped
so conflicts and credential errors are visible rather than retried forever.
Review `systemctl status telegram-bizcollector` and `journalctl -u telegram-bizcollector`.

## Required live acceptance

- Service stays active across a host reboot and a transient network failure.
- An authorized `/start` (or existing BBMA callback for Helix) receives the
  correct response; unauthorized access remains denied.
- No Telegram 409 conflicts or webhook replacement occurs.
- State survives a graceful restart; pending updates are retained.
- A second local process fails immediately without stealing updates.
- Confirm the host uses this exact reviewed commit and the expected bot identity.

## Rollback

Stop the new service first. Restore the previous host configuration and saved
database if necessary. For Actions-owned consumers only, restore repository
variable `TELEGRAM_RUNTIME=actions` after the persistent service is stopped.
Do not run both modes as a fallback race.

## Local verification, 28 October 2026

`python3 -W error::ResourceWarning -m unittest discover -s tests -q`: **213 passed, zero failures**. Python compilation / Node syntax
checks and `git diff --check` passed. Service unit syntax was checked with
`systemd-analyze verify` using temporary copies whose Python executable paths
were substituted for the available interpreter. The real deployment paths,
service user, credentials, host reboot/restart behavior, ledger freshness, and
live Telegram replies remain **unverified**. No paid service was enabled and no
production webhook or deployment was changed.

## Hybrid operation

See [telegram-hybrid.md](telegram-hybrid.md) for the selected listener + Actions
roles, cutover, boundaries, limits and live acceptance gates.
