"""Tests for src/utils/linkedin_auth.py

All tests use unittest.mock — no real LinkedIn or Discord API calls.
Tests are written BEFORE implementation (TDD: they must fail first).
"""
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Module under test — will fail until implementation exists
from src.utils.linkedin_auth import (
    LinkedInAuthError,
    _load_discord_config,
    _load_credentials,
    _post_discord,
    _detect_2fa,
    is_logged_in,
    ensure_logged_in,
    TWO_FA_POLL_INTERVAL,
    TWO_FA_MAX_WAIT,
)


DISCORD_CONFIG = {
    "bot_token": "test-bot-token",
    "channels": {
        "jobs": "1111111111111",
        "night_crew": "2222222222222",
    },
}

SECRETS_YAML = "linkedin_email: test@example.com\nlinkedin_password: secret123\n"


# ---------------------------------------------------------------------------
# _load_discord_config
# ---------------------------------------------------------------------------

class TestLoadDiscordConfig(unittest.TestCase):
    @patch("builtins.open", mock_open(read_data='{"bot_token": "tok", "channels": {}}'))
    @patch("json.load", return_value={"bot_token": "tok", "channels": {}})
    def test_returns_dict(self, mock_json):
        result = _load_discord_config()
        self.assertIn("bot_token", result)


# ---------------------------------------------------------------------------
# _load_credentials
# ---------------------------------------------------------------------------

class TestLoadCredentials(unittest.TestCase):
    @patch("builtins.open", mock_open(read_data=SECRETS_YAML))
    @patch("yaml.safe_load", return_value={"linkedin_email": "test@example.com", "linkedin_password": "secret123"})
    def test_returns_email_and_password(self, mock_yaml):
        email, password = _load_credentials()
        self.assertEqual(email, "test@example.com")
        self.assertEqual(password, "secret123")


# ---------------------------------------------------------------------------
# _post_discord
# ---------------------------------------------------------------------------

class TestPostDiscord(unittest.TestCase):
    @patch("src.utils.linkedin_auth._load_discord_config", return_value=DISCORD_CONFIG)
    @patch("requests.post")
    def test_posts_correct_payload(self, mock_post, mock_cfg):
        mock_post.return_value = MagicMock(status_code=200)
        _post_discord("1111111111111", "hello from test")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["content"], "hello from test")
        self.assertIn("Bot test-bot-token", kwargs["headers"]["Authorization"])

    @patch("src.utils.linkedin_auth._load_discord_config", side_effect=Exception("cfg error"))
    @patch("src.utils.linkedin_auth.logger")
    def test_logs_error_on_failure(self, mock_logger, mock_cfg):
        _post_discord("1111111111111", "msg")
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# _detect_2fa
# ---------------------------------------------------------------------------

class TestDetect2FA(unittest.TestCase):
    def _make_driver(self, page_source):
        driver = MagicMock()
        driver.page_source = page_source
        return driver

    def test_detects_verification_keyword(self):
        driver = self._make_driver("<html>Please complete verification</html>")
        self.assertTrue(_detect_2fa(driver))

    def test_detects_two_step_keyword(self):
        driver = self._make_driver("<html>two-step authentication required</html>")
        self.assertTrue(_detect_2fa(driver))

    def test_detects_security_check_keyword(self):
        driver = self._make_driver("<html>security check in progress</html>")
        self.assertTrue(_detect_2fa(driver))

    def test_detects_pin_keyword(self):
        driver = self._make_driver("<html>Enter your pin to continue</html>")
        self.assertTrue(_detect_2fa(driver))

    def test_no_2fa_keywords_returns_false(self):
        driver = self._make_driver("<html>Welcome to LinkedIn</html>")
        self.assertFalse(_detect_2fa(driver))

    def test_exception_returns_false(self):
        driver = MagicMock()
        type(driver).page_source = property(lambda self: (_ for _ in ()).throw(Exception("err")))
        self.assertFalse(_detect_2fa(driver))


# ---------------------------------------------------------------------------
# is_logged_in
# ---------------------------------------------------------------------------

class TestIsLoggedIn(unittest.TestCase):
    @patch("src.utils.linkedin_auth.WebDriverWait")
    def test_returns_true_when_feed_and_nav_present(self, mock_wait):
        driver = MagicMock()
        driver.current_url = "https://www.linkedin.com/feed/"
        mock_wait.return_value.until.return_value = MagicMock()
        result = is_logged_in(driver)
        self.assertTrue(result)
        driver.get.assert_called_once()

    @patch("src.utils.linkedin_auth.WebDriverWait")
    def test_returns_false_when_nav_not_found(self, mock_wait):
        driver = MagicMock()
        driver.current_url = "https://www.linkedin.com/login"
        from selenium.common.exceptions import TimeoutException
        mock_wait.return_value.until.side_effect = TimeoutException()
        result = is_logged_in(driver)
        self.assertFalse(result)

    @patch("src.utils.linkedin_auth.WebDriverWait")
    def test_returns_false_when_url_not_feed(self, mock_wait):
        driver = MagicMock()
        driver.current_url = "https://www.linkedin.com/checkpoint/challenge"
        mock_wait.return_value.until.return_value = MagicMock()
        result = is_logged_in(driver)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# ensure_logged_in
# ---------------------------------------------------------------------------

class TestEnsureLoggedIn(unittest.TestCase):

    @patch("src.utils.linkedin_auth.is_logged_in", return_value=True)
    def test_skips_login_when_already_logged_in(self, mock_check):
        driver = MagicMock()
        result = ensure_logged_in(driver)
        self.assertTrue(result)
        driver.get.assert_not_called()  # login URL never loaded

    @patch("src.utils.linkedin_auth._load_discord_config", return_value=DISCORD_CONFIG)
    @patch("src.utils.linkedin_auth._load_credentials", return_value=("user@example.com", "pw"))
    @patch("src.utils.linkedin_auth._detect_2fa", return_value=False)
    @patch("src.utils.linkedin_auth.is_logged_in")
    @patch("time.sleep")
    def test_login_flow_when_not_logged_in(self, mock_sleep, mock_is_logged_in, mock_2fa, mock_creds, mock_cfg):
        # First call (session check) → False; after submit → True
        mock_is_logged_in.side_effect = [False, True]
        driver = MagicMock()
        driver.find_element.return_value = MagicMock()
        result = ensure_logged_in(driver)
        self.assertTrue(result)
        driver.get.assert_called()

    @patch("src.utils.linkedin_auth._load_discord_config", return_value=DISCORD_CONFIG)
    @patch("src.utils.linkedin_auth._load_credentials", return_value=("user@example.com", "pw"))
    @patch("src.utils.linkedin_auth._detect_2fa", return_value=True)
    @patch("src.utils.linkedin_auth._post_discord")
    @patch("src.utils.linkedin_auth.is_logged_in")
    @patch("time.sleep")
    def test_2fa_detected_posts_discord_alert(
            self, mock_sleep, mock_is_logged_in, mock_post, mock_2fa, mock_creds, mock_cfg):
        # Session check → False; 2FA poll → True on first poll
        mock_is_logged_in.side_effect = [False, True]
        driver = MagicMock()
        ensure_logged_in(driver)
        mock_post.assert_called_once()
        args = mock_post.call_args[0]
        self.assertIn("2FA", args[1])

    @patch("src.utils.linkedin_auth._load_discord_config", return_value=DISCORD_CONFIG)
    @patch("src.utils.linkedin_auth._load_credentials", return_value=("user@example.com", "pw"))
    @patch("src.utils.linkedin_auth._detect_2fa", return_value=True)
    @patch("src.utils.linkedin_auth._post_discord")
    @patch("src.utils.linkedin_auth.is_logged_in")
    @patch("time.sleep")
    def test_2fa_timeout_raises_linkedin_auth_error(
            self, mock_sleep, mock_is_logged_in, mock_post, mock_2fa, mock_creds, mock_cfg):
        # Session check → False; all 2FA polls → False (never resolves)
        mock_is_logged_in.return_value = False
        driver = MagicMock()
        with self.assertRaises(LinkedInAuthError) as ctx:
            ensure_logged_in(driver)
        self.assertIn("5 minutes", str(ctx.exception))

    @patch("src.utils.linkedin_auth._load_discord_config", return_value=DISCORD_CONFIG)
    @patch("src.utils.linkedin_auth._load_credentials", return_value=("user@example.com", "pw"))
    @patch("src.utils.linkedin_auth._detect_2fa", return_value=False)
    @patch("src.utils.linkedin_auth.is_logged_in")
    @patch("time.sleep")
    def test_bad_credentials_raises_linkedin_auth_error(
            self, mock_sleep, mock_is_logged_in, mock_2fa, mock_creds, mock_cfg):
        # Not logged in before or after login attempt
        mock_is_logged_in.return_value = False
        driver = MagicMock()
        with self.assertRaises(LinkedInAuthError) as ctx:
            ensure_logged_in(driver)
        self.assertIn("credentials", str(ctx.exception))


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    def test_poll_interval_positive(self):
        self.assertGreater(TWO_FA_POLL_INTERVAL, 0)

    def test_max_wait_greater_than_interval(self):
        self.assertGreater(TWO_FA_MAX_WAIT, TWO_FA_POLL_INTERVAL)


if __name__ == "__main__":
    unittest.main()
