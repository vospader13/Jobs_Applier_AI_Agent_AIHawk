"""
TDD tests for Task 5: discord_reporter.py
Tests are written BEFORE implementation (TDD protocol).
All tests mock requests.post and _load_config to avoid real network/disk calls.

conftest.py stubs src.logging before this module loads.
"""
import unittest
from unittest.mock import MagicMock, patch

import src.utils.discord_reporter as reporter

FAKE_CONFIG = {
    "bot_token": "fake-token-abc123",
    "channels": {
        "jobs_applied": "1111111111111111111",
        "jobs_review":  "2222222222222222222",
        "jobs":         "3333333333333333333",
    },
}


class TestSendDailySummary(unittest.TestCase):

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_send_daily_summary_posts_to_jobs_applied_channel(self, mock_post, _cfg):
        """Must POST to the jobs_applied channel ID."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        reporter.send_daily_summary(applied=[], skipped=0, review_count=0)
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        self.assertIn("1111111111111111111", url)

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_send_daily_summary_formats_applied_list(self, mock_post, _cfg):
        """Message must include company, title, fit_score, and counts."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        jobs = [{"company": "Acme", "title": "Engineer", "fit_score": 8}]
        reporter.send_daily_summary(applied=jobs, skipped=2, review_count=1)
        content = mock_post.call_args[1]["json"]["content"]
        self.assertIn("Acme", content)
        self.assertIn("Engineer", content)
        self.assertIn("8", content)
        self.assertIn("Applied: 1", content)
        self.assertIn("Skipped: 2", content)
        self.assertIn("Needs review: 1", content)


class TestSendReviewAlert(unittest.TestCase):

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_send_review_alert_posts_to_jobs_review_channel(self, mock_post, _cfg):
        """Must POST to the jobs_review channel ID."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        reporter.send_review_alert({"title": "Dev", "company": "Corp", "fit_score": 6, "url": "http://x.com"})
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        self.assertIn("2222222222222222222", url)

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_send_review_alert_formats_job_details(self, mock_post, _cfg):
        """Message must include title, company, fit_score, and url."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        job = {"title": "Staff Eng", "company": "TechCo", "fit_score": 7, "url": "https://jobs.example.com/42"}
        reporter.send_review_alert(job)
        content = mock_post.call_args[1]["json"]["content"]
        self.assertIn("Staff Eng", content)
        self.assertIn("TechCo", content)
        self.assertIn("7", content)
        self.assertIn("https://jobs.example.com/42", content)


class TestSendPauseAlert(unittest.TestCase):

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_send_pause_alert_posts_to_jobs_channel(self, mock_post, _cfg):
        """Must POST to the generic jobs channel."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        reporter.send_pause_alert("rate limit hit")
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        self.assertIn("3333333333333333333", url)

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_send_pause_alert_includes_reason(self, mock_post, _cfg):
        """Message must contain the reason string."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        reporter.send_pause_alert("captcha detected")
        content = mock_post.call_args[1]["json"]["content"]
        self.assertIn("captcha detected", content)


class TestSend2faAlert(unittest.TestCase):

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_send_2fa_alert_posts_to_jobs_channel(self, mock_post, _cfg):
        """2FA alert must POST to the generic jobs channel."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        reporter.send_2fa_alert()
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        self.assertIn("3333333333333333333", url)


class TestChunking(unittest.TestCase):

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_long_message_is_chunked(self, mock_post, _cfg):
        """A message longer than 1900 chars must result in multiple POST calls."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        # 25 lines * 101 chars each = 2525 chars total
        long_text = "\n".join(["x" * 100] * 25)
        reporter._send("3333333333333333333", long_text)
        self.assertGreater(mock_post.call_count, 1)
        for c in mock_post.call_args_list:
            chunk_content = c[1]["json"]["content"]
            self.assertLessEqual(len(chunk_content), 1900)


class TestApiFailureHandling(unittest.TestCase):

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_discord_api_failure_does_not_raise(self, mock_post, _cfg):
        """A non-200 response must log an error but NOT raise an exception."""
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
        try:
            reporter._send("3333333333333333333", "test message")
        except Exception as e:
            self.fail(f"_send raised an exception on API failure: {e}")

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post", side_effect=ConnectionError("network down"))
    def test_discord_network_error_does_not_raise(self, mock_post, _cfg):
        """A network exception must be caught and logged, not propagated."""
        try:
            reporter._send("3333333333333333333", "test message")
        except Exception as e:
            self.fail(f"_send raised an exception on network error: {e}")


class TestLoadConfig(unittest.TestCase):

    def test_load_config_reads_discord_json(self):
        """_load_config must return a dict with bot_token and channels keys."""
        result = reporter._load_config()
        self.assertIn("bot_token", result)
        self.assertIn("channels", result)
        self.assertIsInstance(result["channels"], dict)


class TestChunkingNoNewline(unittest.TestCase):

    @patch("src.utils.discord_reporter._load_config", return_value=FAKE_CONFIG)
    @patch("src.utils.discord_reporter.requests.post")
    def test_long_message_no_newline_splits_at_max_len(self, mock_post, _cfg):
        """A message with no newlines longer than 1900 chars must still be split."""
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        # Single block of 2500 chars, no newlines — forces the split_at == -1 branch
        long_text = "y" * 2500
        reporter._send("3333333333333333333", long_text)
        self.assertGreater(mock_post.call_count, 1)
        for c in mock_post.call_args_list:
            chunk_content = c[1]["json"]["content"]
            self.assertLessEqual(len(chunk_content), 1900)


if __name__ == "__main__":
    unittest.main()
