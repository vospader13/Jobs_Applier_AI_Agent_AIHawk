import json
import requests
from datetime import date
from pathlib import Path
from src.logging import logger

DISCORD_CONFIG_PATH = Path("C:/Users/juste/Documents/ElliotBrain/config/discord.json")
DISCORD_API = "https://discord.com/api/v10"
MAX_MSG_LEN = 1900


def _load_config() -> dict:
    with open(DISCORD_CONFIG_PATH) as f:
        return json.load(f)


def _send(channel_id: str, text: str) -> None:
    """Send message to Discord channel, splitting if > 1900 chars."""
    config = _load_config()
    token = config["bot_token"]
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}

    chunks = []
    while len(text) > MAX_MSG_LEN:
        split_at = text.rfind("\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)

    for chunk in chunks:
        try:
            r = requests.post(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                headers=headers,
                json={"content": chunk},
                timeout=10,
            )
            if r.status_code not in (200, 201):
                logger.error(f"Discord send failed: {r.status_code} {r.text}")
        except Exception as e:
            logger.error(f"Discord send error: {e}")


def send_daily_summary(
    applied: list,
    skipped: int,
    review_count: int,
    channel_key: str = "jobs_applied",
) -> None:
    config = _load_config()
    channel_id = config["channels"][channel_key]
    today = date.today().isoformat()

    lines = [
        f"📋 **AutoApply Daily Summary — {today}**",
        f"Applied: {len(applied)} | Skipped: {skipped} | Needs review: {review_count}",
    ]
    for job in applied:
        score = job.get("fit_score", "?")
        lines.append(f"  • {job.get('company', '?')} — {job.get('title', '?')} — fit: {score}")

    _send(channel_id, "\n".join(lines))


def send_review_alert(job: dict) -> None:
    config = _load_config()
    channel_id = config["channels"]["jobs_review"]
    score = job.get("fit_score", "?")
    title = job.get("title", "?")
    company = job.get("company", "?")
    url = job.get("url", "")

    msg = (
        f"👀 **Review Required** — fit score {score}/10\n"
        f"**{title}** at **{company}**\n"
        f"{url}\n"
        f"Apply? React ✅ to approve or ❌ to skip."
    )
    _send(channel_id, msg)


def send_pause_alert(reason: str, daily_count: int = 0) -> None:
    config = _load_config()
    channel_id = config["channels"]["jobs"]
    msg = f"🚨 **AutoApply PAUSED** — {reason}\nManual intervention required. Bot is waiting."
    _send(channel_id, msg)


def send_2fa_alert() -> None:
    config = _load_config()
    channel_id = config["channels"]["jobs"]
    msg = (
        "🔐 **LinkedIn 2FA Required**\n"
        "Open LinkedIn and complete verification, then press continue.\n"
        "Pausing for up to 5 minutes."
    )
    _send(channel_id, msg)
