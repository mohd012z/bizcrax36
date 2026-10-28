# Telegram shortcut menu

Telegram's command shortcut menu is configured through the Bot API method `setMyCommands`. Adding a list of commands to source code alone does not register it with Telegram.

This branch defines commands in `worker/telegram.js`: /start, /research, /status, /sector, /help.

Once the Worker is deployed with `TELEGRAM_BOT_TOKEN`, invoke the exported `registerBotCommands(env)` from a protected one-time deployment administration task. Do not expose a public HTTP registration endpoint.

The existing inline keyboard remains available. BotFather /setcommands is an alternative for manual configuration, but registration through the Bot API is preferred for automation.

No live Telegram registration has occurred until the authenticated Bot API call succeeds.
