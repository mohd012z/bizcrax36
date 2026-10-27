# Telegram inline menu on GitHub Actions

BizCrax36 uses the same Telegram BotFather bot **@bizcollectorbot** and existing repository secrets:

- `TELEGRAM_BOT_TOKEN`: BotFather token (secret; never share or commit).
- `TELEGRAM_CHAT_ID`: the permitted chat ID, used as the default allowlist.

The workflow [telegram-interactive.yml](../.github/workflows/telegram-interactive.yml) runs `python -m backend.telegram_poll_once` every five minutes, and can also be started with **Run workflow**. It polls Telegram's `getUpdates`, sends the response and inline keyboard, and acknowledges the update after a successful send. GitHub Actions runners are ephemeral; Telegram holds unacknowledged updates between runs. If a runner fails after sending but before acknowledging, a duplicate reply is possible.

## First-use test

1. Ensure the two secrets above are configured in **Settings → Secrets and variables → Actions**. The chat ID must be numeric and belong to the chat you are testing.
2. In Telegram send `/start` to @bizcollectorbot.
3. Open **Actions → BizCrax36 Telegram interactive menu → Run workflow** on the `main` branch.
4. Check that the run succeeded and that Telegram receives the welcome text and inline buttons.
5. Tap **Sector ▾** and rerun the workflow; the submenu should appear.
6. Tap **Energy**, rerun the workflow; the bot should show research results. Try `/search energy` as a text command.

## Important limitations

- GitHub Actions **cannot provide instant responses**. Five-minute cron is best-effort and may run late or be skipped under load. Do not expect an immediate reply after tapping.
- Scheduled workflows only execute from the default branch. If the workflow is disabled by GitHub, enable it in the Actions UI.
- A webhook or another polling bot using the same token can consume the updates first. Use only one interactive update consumer.
- This workflow reads committed business ideas and any local database available to its runner. It does **not** yet retrieve a persistent database from a separate collector job. The `/live` menu will be empty until issuer-verified records are provided.
- The menu is an inline-keyboard submenu, not a native Telegram dropdown.
- The separate **Telegram research digest** workflow sends outbound messages; it does not respond to commands.
- The bot restricts incoming commands by chat ID and does not reveal secrets in logs.
