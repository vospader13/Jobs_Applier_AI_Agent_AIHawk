"""
tests/test_indeed_handler.py

Failing tests for Issue #13: Phase 1 — Indeed Easy Apply handler.
Tests are written BEFORE implementation (TDD).
"""
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Stub src.logging before any module under test is imported
# ---------------------------------------------------------------------------
if "src.logging" not in sys.modules:
    _logging_stub = types.ModuleType("src.logging")
    _logging_stub.logger = MagicMock()
    sys.modules["src.logging"] = _logging_stub

# Stub src.utils.discord_reporter so we can assert on send_pause_alert calls
_discord_stub = types.ModuleType("src.utils.discord_reporter")
_discord_stub.send_pause_alert = MagicMock()
sys.modules["src.utils.discord_reporter"] = _discord_stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler(answer_bank=None):
    """Return an IndeedApplyHandler with mocked driver and llm_manager."""
    from src.ai_hawk.indeed_handler import IndeedApplyHandler

    driver = MagicMock()
    llm_manager = MagicMock()
    return IndeedApplyHandler(
        driver=driver,
        llm_manager=llm_manager,
        answer_bank=answer_bank or {},
    )


def _job(salary_max=None, title="Software Engineer", company="Acme", url="https://indeed.com/job/1"):
    """Return a minimal job dict."""
    return {"title": title, "company": company, "url": url, "salary_max": salary_max}


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------

class TestImport:
    def test_indeed_handler_is_importable(self):
        """IndeedApplyHandler must be importable from src.ai_hawk.indeed_handler."""
        from src.ai_hawk.indeed_handler import IndeedApplyHandler  # noqa: F401
        assert IndeedApplyHandler is not None

    def test_indeed_handler_exported_from_package(self):
        """IndeedApplyHandler must be accessible via src.ai_hawk."""
        import src.ai_hawk as pkg
        assert hasattr(pkg, "IndeedApplyHandler"), (
            "IndeedApplyHandler not exported from src/ai_hawk/__init__.py"
        )


# ---------------------------------------------------------------------------
# _should_skip tests
# ---------------------------------------------------------------------------

class TestShouldSkip:
    def test_skip_when_salary_max_below_100k(self):
        """_should_skip returns True when salary_max < 100000."""
        handler = _make_handler()
        job = _job(salary_max=80000)
        assert handler._should_skip(job) is True

    def test_skip_when_salary_max_exactly_99999(self):
        """_should_skip returns True for salary_max = 99999."""
        handler = _make_handler()
        assert handler._should_skip(_job(salary_max=99999)) is True

    def test_no_skip_when_salary_max_is_150k(self):
        """_should_skip returns False for a normal $150k job."""
        handler = _make_handler()
        job = _job(salary_max=150000)
        assert handler._should_skip(job) is False

    def test_no_skip_when_salary_max_is_none(self):
        """_should_skip returns False when salary_max is not listed."""
        handler = _make_handler()
        job = _job(salary_max=None)
        assert handler._should_skip(job) is False

    def test_no_skip_when_salary_max_exactly_100k(self):
        """_should_skip returns False when salary_max == 100000 (boundary)."""
        handler = _make_handler()
        assert handler._should_skip(_job(salary_max=100000)) is False


# ---------------------------------------------------------------------------
# Daily cap tests
# ---------------------------------------------------------------------------

class TestDailyCap:
    def test_apply_raises_after_30_calls(self):
        """apply raises RuntimeError (or similar) after 30 successful applications."""
        handler = _make_handler()

        # Force _should_skip to always return False and _do_apply to succeed
        handler._should_skip = MagicMock(return_value=False)
        handler._do_apply = MagicMock(return_value=True)

        job = _job()
        # First 30 calls should succeed
        for _ in range(30):
            handler.apply(job)

        # 31st call must raise or send alert and stop
        with pytest.raises(Exception):
            handler.apply(job)

    def test_daily_cap_triggers_discord_alert(self):
        """Discord pause alert fires when daily cap is reached."""
        from src.utils.discord_reporter import send_pause_alert

        send_pause_alert.reset_mock()

        handler = _make_handler()
        handler._should_skip = MagicMock(return_value=False)
        handler._do_apply = MagicMock(return_value=True)

        job = _job()
        for _ in range(30):
            handler.apply(job)

        try:
            handler.apply(job)
        except Exception:
            pass

        send_pause_alert.assert_called()
        # The call reason must mention cap
        call_reason = send_pause_alert.call_args[0][0] if send_pause_alert.call_args[0] else \
            send_pause_alert.call_args[1].get("reason", "")
        assert "cap" in call_reason.lower() or "daily" in call_reason.lower()

    def test_applications_today_counter_increments(self):
        """applications_today counter increments on each successful apply."""
        handler = _make_handler()
        handler._should_skip = MagicMock(return_value=False)
        handler._do_apply = MagicMock(return_value=True)

        job = _job()
        handler.apply(job)
        handler.apply(job)
        assert handler.applications_today == 2


# ---------------------------------------------------------------------------
# _fill_form_field tests
# ---------------------------------------------------------------------------

class TestFillFormField:
    def test_answer_bank_used_before_llm(self):
        """_fill_form_field checks answer_bank before calling llm_manager.invoke."""
        answer_bank = {"years of experience": "5"}
        handler = _make_handler(answer_bank=answer_bank)

        field_element = MagicMock()
        handler._fill_form_field(field_element, "Years of Experience")

        # LLM must NOT have been called
        handler.llm_manager.invoke.assert_not_called()

    def test_llm_called_when_answer_not_in_bank(self):
        """_fill_form_field calls llm_manager.invoke when question not in answer_bank."""
        handler = _make_handler(answer_bank={})
        handler.llm_manager.invoke.return_value = MagicMock(content="3 years")

        field_element = MagicMock()
        handler._fill_form_field(field_element, "What is your notice period?")

        handler.llm_manager.invoke.assert_called_once()

    def test_answer_bank_lookup_is_case_insensitive(self):
        """answer_bank lookup normalises key case."""
        answer_bank = {"Years Of Experience": "7"}
        handler = _make_handler(answer_bank=answer_bank)

        field_element = MagicMock()
        handler._fill_form_field(field_element, "years of experience")
        handler.llm_manager.invoke.assert_not_called()


# ---------------------------------------------------------------------------
# Consecutive failures / Discord alert
# ---------------------------------------------------------------------------

class TestConsecutiveFailures:
    def test_discord_alert_after_3_consecutive_failures(self):
        """After 3 consecutive failures, send_pause_alert is called and an exception raised."""
        from src.utils.discord_reporter import send_pause_alert

        send_pause_alert.reset_mock()

        handler = _make_handler()
        handler._should_skip = MagicMock(return_value=False)
        handler._do_apply = MagicMock(side_effect=Exception("apply failed"))

        job = _job()
        with pytest.raises(Exception):
            for _ in range(4):
                try:
                    handler.apply(job)
                except Exception as exc:
                    # Re-raise only when it's the escalation raise (after 3 failures)
                    if "consecutive" in str(exc).lower() or "pause" in str(exc).lower():
                        raise
                    # Regular failure — keep counting
                    continue

        send_pause_alert.assert_called()
