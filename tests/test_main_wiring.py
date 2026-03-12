"""
test_main_wiring.py — TDD tests for Issue #12.

Verifies:
  1. AIHawkBotFacade can be imported from src.ai_hawk.bot_facade
  2. AIHawkJobManager can be imported from src.ai_hawk (via __init__.py)
  3. The CLI has a 'run' command registered on the cli group in main.py
"""
import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — stub heavy optional deps so import tests stay unit-level
# ---------------------------------------------------------------------------

def _stub_module(name: str) -> types.ModuleType:
    """Register a lightweight MagicMock module in sys.modules."""
    mod = types.ModuleType(name)
    sys.modules.setdefault(name, mod)
    return mod


def _ensure_selenium_stubs() -> None:
    """Stub selenium and webdriver_manager so imports don't need the real wheels."""
    for name in [
        "selenium",
        "selenium.webdriver",
        "selenium.webdriver.common",
        "selenium.webdriver.common.by",
        "selenium.webdriver.support",
        "selenium.webdriver.support.expected_conditions",
        "selenium.webdriver.support.ui",
        "selenium.common",
        "selenium.common.exceptions",
        "selenium.webdriver.chrome",
        "selenium.webdriver.chrome.service",
        "webdriver_manager",
        "webdriver_manager.chrome",
        "inquirer",
    ]:
        _stub_module(name)

    # Give By.CLASS_NAME etc. real-ish attributes
    by_mod = sys.modules["selenium.webdriver.common.by"]
    by_class = type("By", (), {"CLASS_NAME": "class_name", "XPATH": "xpath"})
    by_mod.By = by_class

    # WebDriverWait / EC stubs
    wdw_mod = sys.modules["selenium.webdriver.support.ui"]
    wdw_mod.WebDriverWait = MagicMock()
    ec_mod = sys.modules["selenium.webdriver.support.expected_conditions"]
    ec_mod.presence_of_element_located = MagicMock()

    exc_mod = sys.modules["selenium.common.exceptions"]
    exc_mod.NoSuchElementException = Exception
    exc_mod.TimeoutException = Exception
    exc_mod.WebDriverException = Exception

    svc_mod = sys.modules["selenium.webdriver.chrome.service"]
    svc_mod.Service = MagicMock()

    cdm_mod = sys.modules["webdriver_manager.chrome"]
    cdm_mod.ChromeDriverManager = MagicMock()


# ---------------------------------------------------------------------------
# Test 1: AIHawkBotFacade importable from src.ai_hawk.bot_facade
# ---------------------------------------------------------------------------

class TestBotFacadeImport:
    """AIHawkBotFacade must be importable from src.ai_hawk.bot_facade."""

    def test_aihawk_bot_facade_importable(self):
        """Importing AIHawkBotFacade should not raise."""
        _ensure_selenium_stubs()
        # Stub discord_reporter dependency
        _stub_module("src.utils.discord_reporter").send_pause_alert = MagicMock()
        _stub_module("src.utils.linkedin_auth").ensure_logged_in = MagicMock()

        from src.ai_hawk.bot_facade import AIHawkBotFacade  # noqa: F401
        assert AIHawkBotFacade is not None

    def test_aihawk_bot_facade_is_a_class(self):
        """AIHawkBotFacade must be a class (not a function or module)."""
        _ensure_selenium_stubs()
        from src.ai_hawk.bot_facade import AIHawkBotFacade
        assert isinstance(AIHawkBotFacade, type)


# ---------------------------------------------------------------------------
# Test 2: AIHawkJobManager importable from src.ai_hawk
# ---------------------------------------------------------------------------

class TestAIHawkInitExports:
    """src.ai_hawk.__init__ must export AIHawkBotFacade and AIHawkJobManager."""

    def test_ai_hawk_init_exports_aihawk_bot_facade(self):
        """from src.ai_hawk import AIHawkBotFacade must succeed."""
        _ensure_selenium_stubs()
        _stub_module("src.utils.discord_reporter").send_pause_alert = MagicMock()
        _stub_module("src.utils.linkedin_auth").ensure_logged_in = MagicMock()

        import src.ai_hawk as ai_hawk_pkg
        importlib.reload(ai_hawk_pkg)
        assert hasattr(ai_hawk_pkg, "AIHawkBotFacade"), (
            "src.ai_hawk.__init__ must export AIHawkBotFacade"
        )

    def test_ai_hawk_init_exports_aihawk_job_manager(self):
        """from src.ai_hawk import AIHawkJobManager must succeed."""
        _ensure_selenium_stubs()

        import src.ai_hawk as ai_hawk_pkg
        importlib.reload(ai_hawk_pkg)
        assert hasattr(ai_hawk_pkg, "AIHawkJobManager"), (
            "src.ai_hawk.__init__ must export AIHawkJobManager"
        )


# ---------------------------------------------------------------------------
# Test 3: main.py CLI group has a 'run' command
# ---------------------------------------------------------------------------

class TestMainCliRunCommand:
    """The Click cli group in main.py must register a 'run' command."""

    def _load_cli(self):
        """Import main module (fresh) and return the cli Click group."""
        _ensure_selenium_stubs()

        # Stub heavy main.py imports
        _stub_module("src.utils.discord_reporter").send_pause_alert = MagicMock()
        _stub_module("src.utils.linkedin_auth").ensure_logged_in = MagicMock()

        for name in [
            "src.libs.resume_and_cover_builder",
            "src.resume_schemas.job_application_profile",
            "src.resume_schemas.resume",
            "src.utils.chrome_utils",
            "src.utils.constants",
        ]:
            mod = _stub_module(name)
            # Provide attribute names consumed by main.py
            mod.ResumeFacade = MagicMock()
            mod.ResumeGenerator = MagicMock()
            mod.StyleManager = MagicMock()
            mod.JobApplicationProfile = MagicMock()
            mod.Resume = MagicMock()
            mod.init_browser = MagicMock()
            mod.PLAIN_TEXT_RESUME_YAML = "plain_text_resume.yaml"
            mod.SECRETS_YAML = "secrets.yaml"
            mod.WORK_PREFERENCES_YAML = "work_preferences.yaml"

        # Force reimport of main
        sys.modules.pop("main", None)
        import main as main_mod
        return main_mod

    def test_cli_group_exists(self):
        """main module must expose a 'cli' Click group."""
        main_mod = self._load_cli()
        assert hasattr(main_mod, "cli"), "main.py must define a Click 'cli' group"

    def test_cli_has_run_command(self):
        """The 'cli' group must have a registered 'run' command."""
        main_mod = self._load_cli()
        assert "run" in main_mod.cli.commands, (
            "cli group must register a 'run' command via @cli.command()"
        )
