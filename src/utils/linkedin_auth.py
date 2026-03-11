import os
import time
import json
import requests
import yaml
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from src.logging import logger

DISCORD_CONFIG_PATH = Path(os.environ.get(
    "ELLIOT_DISCORD_CONFIG",
    "C:/Users/juste/Documents/ElliotBrain/config/discord.json",
))
SECRETS_PATH = Path("data_folder/secrets.yaml")
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed"
TWO_FA_POLL_INTERVAL = 15  # seconds
TWO_FA_MAX_WAIT = 300  # 5 minutes


class LinkedInAuthError(Exception):
    pass


def _load_discord_config() -> dict:
    with open(DISCORD_CONFIG_PATH) as f:
        return json.load(f)


def _load_credentials() -> tuple:
    with open(SECRETS_PATH) as f:
        secrets = yaml.safe_load(f)
    return secrets["linkedin_email"], secrets["linkedin_password"]


def _post_discord(channel_id: str, message: str) -> None:
    try:
        config = _load_discord_config()
        token = config["bot_token"]
        requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"content": message},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Discord alert failed: {e}")


def is_logged_in(driver) -> bool:
    try:
        driver.get(LINKEDIN_FEED_URL)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "nav.global-nav"))
        )
        return "feed" in driver.current_url
    except Exception:
        return False


def _detect_2fa(driver) -> bool:
    try:
        page_src = driver.page_source.lower()
        return any(kw in page_src for kw in ["verification", "two-step", "security check", "pin"])
    except Exception:
        return False


def ensure_logged_in(driver) -> bool:
    if is_logged_in(driver):
        logger.info("LinkedIn session active -- skipping login.")
        return True

    logger.info("No active LinkedIn session. Attempting login...")
    email, password = _load_credentials()
    config = _load_discord_config()
    jobs_channel = config["channels"]["jobs"]

    try:
        driver.get(LINKEDIN_LOGIN_URL)
        time.sleep(2)
        driver.find_element(By.ID, "username").send_keys(email)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(3)

        if _detect_2fa(driver):
            logger.warning("LinkedIn 2FA prompt detected.")
            _post_discord(
                jobs_channel,
                "LinkedIn 2FA required -- open LinkedIn and complete verification, then press continue. "
                "Pausing for up to 5 minutes.",
            )

            elapsed = 0
            while elapsed < TWO_FA_MAX_WAIT:
                time.sleep(TWO_FA_POLL_INTERVAL)
                elapsed += TWO_FA_POLL_INTERVAL
                if is_logged_in(driver):
                    logger.info("2FA completed. Session active.")
                    return True

            raise LinkedInAuthError("2FA not completed within 5 minutes. Aborting.")

        if is_logged_in(driver):
            logger.info("Login successful.")
            return True

        raise LinkedInAuthError("Login failed -- check credentials.")

    except LinkedInAuthError:
        raise
    except Exception as e:
        raise LinkedInAuthError(f"Unexpected auth error: {e}")
