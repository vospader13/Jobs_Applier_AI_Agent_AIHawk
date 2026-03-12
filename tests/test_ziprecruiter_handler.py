"""
tests/test_ziprecruiter_handler.py

Failing tests for ZipRecruiterApplyHandler (Issue #14).
Written BEFORE implementation — all tests must FAIL on first run.
"""
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Stubs — must be registered before the module under test is imported
# ---------------------------------------------------------------------------

# src.logging stub (conftest may already register this, but we ensure it here)
if "src.logging" not in sys.modules:
    _logging_stub = types.ModuleType("src.logging")
    _logging_stub.logger = MagicMock()
    sys.modules["src.logging"] = _logging_stub

# selenium stubs
for _mod in [
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.common",
    "selenium.webdriver.common.by",
    "selenium.webdriver.support",
    "selenium.webdriver.support.ui",
    "selenium.webdriver.support.expected_conditions",
    "selenium.common",
    "selenium.common.exceptions",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# Populate the specific attributes tests and implementation need
_by = sys.modules["selenium.webdriver.common.by"]
_by.By = MagicMock()

_ec = sys.modules["selenium.webdriver.support.expected_conditions"]
_ec.element_to_be_clickable = MagicMock()
_ec.presence_of_element_located = MagicMock()

_ui = sys.modules["selenium.webdriver.support.ui"]
_ui.WebDriverWait = MagicMock()
_ui.Select = MagicMock()

_exc = sys.modules["selenium.common.exceptions"]
_exc.NoSuchElementException = type("NoSuchElementException", (Exception,), {})
_exc.TimeoutException = type("TimeoutException", (Exception,), {})
_exc.ElementNotInteractableException = type("ElementNotInteractableException", (Exception,), {})

# discord_reporter stub
if "src.utils.discord_reporter" not in sys.modules:
    _dr = types.ModuleType("src.utils.discord_reporter")
    _dr.send_pause_alert = MagicMock()
    sys.modules["src.utils"] = types.ModuleType("src.utils")
    sys.modules["src.utils.discord_reporter"] = _dr

# ---------------------------------------------------------------------------
# Import the module under test (will FAIL until implementation exists)
# ---------------------------------------------------------------------------

from src.ai_hawk.ziprecruiter_handler import ZipRecruiterApplyHandler  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_driver():
    return MagicMock()


@pytest.fixture()
def mock_llm():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="LLM answer")
    return llm


@pytest.fixture()
def answer_bank():
    return {"years of experience": "5", "preferred salary": "150000"}


@pytest.fixture()
def handler(mock_driver, mock_llm, answer_bank):
    return ZipRecruiterApplyHandler(
        driver=mock_driver,
        llm_manager=mock_llm,
        answer_bank=answer_bank,
    )


@pytest.fixture()
def normal_job():
    return {
        "role": "Software Engineer",
        "company": "Acme Corp",
        "url": "https://www.ziprecruiter.com/jobs/acme-12345",
        "salary_max": 150000,
    }


@pytest.fixture()
def low_salary_job():
    return {
        "role": "Junior Dev",
        "company": "Cheapo Inc",
        "url": "https://www.ziprecruiter.com/jobs/cheapo-99999",
        "salary_max": 80000,
    }


# ---------------------------------------------------------------------------
# 1. Import / instantiation
# ---------------------------------------------------------------------------

class TestImportAndInit:
    def test_importable(self):
        """ZipRecruiterApplyHandler must be importable from src.ai_hawk.ziprecruiter_handler."""
        assert ZipRecruiterApplyHandler is not None

    def test_initial_state(self, handler):
        """Handler initialises with zero applications and DAILY_CAP=50."""
        assert handler.applications_today == 0
        assert handler.DAILY_CAP == 50
        assert handler.consecutive_failures == 0


# ---------------------------------------------------------------------------
# 2. _is_one_click
# ---------------------------------------------------------------------------

class TestIsOneClick:
    def test_returns_true_when_button_present(self, handler, mock_driver):
        """_is_one_click returns True when a '1-Click Apply' element is in the DOM."""
        btn = MagicMock()
        btn.get_attribute.return_value = "1-Click Apply"
        mock_driver.find_elements.return_value = [btn]
        assert handler._is_one_click() is True

    def test_returns_false_when_no_button(self, handler, mock_driver):
        """_is_one_click returns False when no '1-Click Apply' element exists."""
        mock_driver.find_elements.return_value = []
        assert handler._is_one_click() is False

    def test_returns_false_when_aria_label_differs(self, handler, mock_driver):
        """_is_one_click returns False when the button has a different aria-label."""
        btn = MagicMock()
        btn.get_attribute.return_value = "Easy Apply"
        mock_driver.find_elements.return_value = [btn]
        assert handler._is_one_click() is False


# ---------------------------------------------------------------------------
# 3. _should_skip
# ---------------------------------------------------------------------------

class TestShouldSkip:
    def test_skips_when_salary_max_below_100k(self, handler, low_salary_job):
        """_should_skip returns True when listed salary max < $100,000."""
        assert handler._should_skip(low_salary_job) is True

    def test_does_not_skip_normal_job(self, handler, normal_job):
        """_should_skip returns False for a job with acceptable salary."""
        assert handler._should_skip(normal_job) is False

    def test_does_not_skip_when_no_salary_key(self, handler):
        """_should_skip returns False when salary_max is absent from the job dict."""
        job = {"role": "Dev", "company": "Foo", "url": "https://ziprecruiter.com/j/1"}
        assert handler._should_skip(job) is False

    def test_does_not_skip_at_exactly_100k(self, handler):
        """_should_skip returns False when salary_max == 100000 (boundary)."""
        job = {
            "role": "Dev",
            "company": "Foo",
            "url": "https://ziprecruiter.com/j/2",
            "salary_max": 100000,
        }
        assert handler._should_skip(job) is False


# ---------------------------------------------------------------------------
# 4. Daily cap enforcement in apply()
# ---------------------------------------------------------------------------

class TestDailyCap:
    def test_raises_after_50_applications(self, handler, normal_job):
        """apply() raises RuntimeError (or similar) after DAILY_CAP submissions."""
        handler.applications_today = 50

        with patch(
            "src.utils.discord_reporter.send_pause_alert"
        ) as mock_alert, patch(
            "src.ai_hawk.ziprecruiter_handler.send_pause_alert"
        ) as mock_alert2:
            with pytest.raises(Exception):
                handler.apply(normal_job)

    def test_sends_discord_alert_at_cap(self, handler, normal_job):
        """apply() calls send_pause_alert when the daily cap is hit."""
        handler.applications_today = 50

        with patch(
            "src.ai_hawk.ziprecruiter_handler.send_pause_alert"
        ) as mock_alert:
            with pytest.raises(Exception):
                handler.apply(normal_job)
            mock_alert.assert_called_once()

    def test_increments_counter_on_success(self, handler, mock_driver, normal_job):
        """apply() increments applications_today on a successful one-click apply."""
        # Simulate one-click path: button found, click succeeds, modal confirmed
        btn = MagicMock()
        btn.get_attribute.return_value = "1-Click Apply"
        mock_driver.find_elements.return_value = [btn]
        mock_driver.find_element.return_value = MagicMock()
        mock_driver.page_source = "<html>success</html>"

        with patch("time.sleep"):
            result = handler.apply(normal_job)

        assert handler.applications_today == 1
        assert result is True


# ---------------------------------------------------------------------------
# 5. _fill_form_field — answer_bank lookup before LLM
# ---------------------------------------------------------------------------

class TestFillFormField:
    def test_uses_answer_bank_before_llm(self, handler, mock_llm):
        """_fill_form_field uses answer_bank hit and does NOT call LLM."""
        field = MagicMock()
        field.get_attribute.return_value = "text"

        handler._fill_form_field(field, "years of experience")

        mock_llm.invoke.assert_not_called()
        field.clear.assert_called_once()
        field.send_keys.assert_called_once_with("5")

    def test_falls_back_to_llm_when_not_in_answer_bank(self, handler, mock_llm):
        """_fill_form_field calls LLM when question is not in answer_bank."""
        field = MagicMock()
        field.get_attribute.return_value = "text"

        handler._fill_form_field(field, "what is your greatest weakness?")

        mock_llm.invoke.assert_called_once()
        field.send_keys.assert_called()

    def test_answer_bank_lookup_is_case_insensitive(self, handler, mock_llm):
        """_fill_form_field matches answer_bank keys case-insensitively."""
        field = MagicMock()
        field.get_attribute.return_value = "text"

        handler._fill_form_field(field, "Years Of Experience")

        mock_llm.invoke.assert_not_called()
        field.send_keys.assert_called_once_with("5")


# ---------------------------------------------------------------------------
# 6. Three consecutive failures trigger Discord alert + raise
# ---------------------------------------------------------------------------

class TestConsecutiveFailures:
    def test_three_failures_trigger_alert_and_raise(self, handler, mock_driver, normal_job):
        """After 3 consecutive failures apply() sends Discord alert and raises."""
        # Make _is_one_click return False and multi-step form fail
        mock_driver.find_elements.return_value = []
        mock_driver.find_element.side_effect = Exception("element not found")

        with patch("src.ai_hawk.ziprecruiter_handler.send_pause_alert") as mock_alert:
            for _ in range(2):
                try:
                    handler.apply(normal_job)
                except Exception:
                    pass

            with pytest.raises(Exception):
                handler.apply(normal_job)

            mock_alert.assert_called()
            alert_call_args = mock_alert.call_args[0][0] if mock_alert.call_args else ""
            assert "consecutive" in alert_call_args.lower() or mock_alert.called


# ---------------------------------------------------------------------------
# 7. CAPTCHA detection
# ---------------------------------------------------------------------------

class TestCaptchaDetection:
    def test_captcha_in_page_source_triggers_alert(self, handler, mock_driver, normal_job):
        """apply() detects 'captcha' in page_source and calls send_pause_alert."""
        mock_driver.page_source = "<html>please solve the captcha challenge</html>"
        mock_driver.find_elements.return_value = []

        with patch("src.ai_hawk.ziprecruiter_handler.send_pause_alert") as mock_alert:
            with pytest.raises(Exception):
                handler.apply(normal_job)
            mock_alert.assert_called()
