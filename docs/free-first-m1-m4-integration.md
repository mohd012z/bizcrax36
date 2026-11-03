# Free-first M1–M4 integration (development branch only)

## Delivered in this branch
- Telegram native command definitions and parser (registration not automatic)
- Versioned JSON and CSV validation, import and export
- Durable SQLite update deduplication for one consumer
- Unit tests (run `python -m unittest tests.test_free_reliability -v`)

## Production rollout gates
1. Run existing tests: `python -m unittest discover -s tests -v`.
2. Select exactly one Telegram receiver: continuous long polling **or** HTTPS webhook.
3. Register commands by calling Telegram `setMyCommands` with `command_payload()`; verify with `getMyCommands`.
4. Wire commands to existing `telegram_poll_once.py` dispatch. Do not advertise unsupported commands before wiring.
5. Use `UpdateLedger` in the single receiver, mark after successful processing. For multi-worker hosting, replace SQLite with shared PostgreSQL and transactional claims.
6. For document import, use Telegram `getFile`, check allowlisted chat ID, file extension, MIME and byte limits, then call `import_data`. Do not overwrite existing data without review.
7. For export, use `export_data` and Telegram multipart `sendDocument`. Validate returned success.
8. Generate and retain source manifests and hashes for every report.
9. Confirm a real Telegram /start, /research, inline callback, upload and export; confirm duplicate update replay is harmless.

## Important limits
- This patch is additive and does not alter live bot behavior.
- SQLite works only with persistent disk and one active consumer.
- Document support is JSON/CSV only. PDF/OCR/XLSX require separate implementation.
- A processed-update ledger prevents reprocessing after marking; delivery and marking are not atomic.
- Do not use GitHub Actions scheduling as a substitute for real-time Telegram updates.
