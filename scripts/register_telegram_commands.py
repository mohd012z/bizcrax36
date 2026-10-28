"""Register Telegram slash commands using the repository's bot secret."""
import json
import os
from urllib.request import Request, urlopen

COMMANDS = [
    {"command": "start", "description": "Open BizCrax36 menu"},
    {"command": "research", "description": "Research a business opportunity"},
    {"command": "status", "description": "Check bot status"},
    {"command": "sector", "description": "Browse business sectors"},
    {"command": "help", "description": "Commands and instructions"},
]


def register(token, opener=urlopen):
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    payload = json.dumps({"commands": COMMANDS, "scope": {"type": "default"}}).encode()
    request = Request(
        "https://api.telegram.org/bot" + token + "/setMyCommands",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener(request, timeout=20) as response:
        result = json.load(response)
    if result.get("ok") is not True or result.get("result") is not True:
        raise RuntimeError("Telegram rejected command registration")
    return True


if __name__ == "__main__":
    register(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    print("Telegram command shortcuts registered")
