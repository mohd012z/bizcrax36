# BizCrax36 Telegram bot (@bizcollectorbot)

The Telegram adapter provides **read-only** search of the same local SQLite research database and idea files as the HTML dashboard. It does not automatically create, configure or deploy a Telegram bot, and does not collect tenders on its own.

## Setup
1. Create or confirm ownership of **@bizcollectorbot** using Telegram's official @BotFather. Do not paste the bot token into GitHub, chat, screenshots or source code.
2. Configure the token as an environment variable **TELEGRAM_BOT_TOKEN** on the private runtime host.
3. Configure **TELEGRAM_ALLOWED_CHAT_IDS** as a comma-separated list of numeric chat IDs. The bot rejects messages from all other chats. Obtain the IDs securely using Telegram's own update data or a trusted admin workflow.
4. Run the existing collector (e.g. `python -m backend.collect_to_db`) to populate `data/research.sqlite3`. This collector is not automatically scheduled by the Telegram process.
5. Start the bot with `python -m backend.telegram_bot` on an always-on machine with network access. Long polling uses Telegram's official API and does not require a public inbound port.

Commands: `/help`, `/status`, `/search energy`, `/ideas aviation`, `/live software`.

## Operational notes
- The bot is **not running** until the owner configures the token, chat IDs, database and hosting.
- All opportunity results must be treated as research leads. The live filter requires issuer verification, not merely publication on a portal.
- The current bot returns up to five results per query and does not write to the database.
- Never commit tokens. Use deployment secrets and rotate compromised credentials.
- Run only one polling instance per token; a webhook and long polling should not be enabled simultaneously.
- GitHub Actions CI tests do not deploy the bot.
