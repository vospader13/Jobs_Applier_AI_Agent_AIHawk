"""
TDD tests for Task 2: chrome_utils.py with undetected-chromedriver + persistent profile.
Tests are written BEFORE implementation (TDD protocol).
"""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Ensure the repo root is on sys.path so `src` resolves as a real package
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Minimal stub for undetected_chromedriver installed BEFORE importing module
# ---------------------------------------------------------------------------
def _install_uc_stub():
    uc_mod = types.ModuleType("undetected_chromedriver")

    class FakeChromeOptions:
        def __init__(self):
            self._arguments = []

        def add_argument(self, arg):
            self._arguments.append(arg)

    class FakeChrome:
        pass

    uc_mod.ChromeOptions = FakeChromeOptions
    uc_mod.Chrome = FakeChrome
    sys.modules["undetected_chromedriver"] = uc_mod
    return uc_mod


_uc_stub = _install_uc_stub()

# Stub src.logging so loguru is not required
_logging_mod = types.ModuleType("src.logging")
_logging_mod.logger = MagicMock()
sys.modules["src.logging"] = _logging_mod

# Import module under test
from src.utils import chrome_utils  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestChromeBrowserOptions(unittest.TestCase):
    """chrome_browser_options() returns a uc.ChromeOptions with correct args."""

    def setUp(self):
        self.options = chrome_utils.chrome_browser_options()

    def test_returns_chrome_options_instance(self):
        """Result must be a uc.ChromeOptions (or stub equivalent)."""
        import undetected_chromedriver as uc
        self.assertIsInstance(self.options, uc.ChromeOptions)

    def test_no_incognito_flag(self):
        """--incognito must NOT be present in the options arguments."""
        args = self.options._arguments
        self.assertNotIn("--incognito", args,
                         "--incognito must be absent (persistent profile mode)")

    def test_user_data_dir_is_set(self):
        """--user-data-dir must appear exactly once in the options arguments."""
        args = self.options._arguments
        user_data_args = [a for a in args if a.startswith("--user-data-dir=")]
        self.assertEqual(
            len(user_data_args), 1,
            f"Expected exactly one --user-data-dir argument, got: {user_data_args}"
        )

    def test_user_data_dir_points_to_profile(self):
        """--user-data-dir value must contain 'chrome_profile'."""
        args = self.options._arguments
        user_data_args = [a for a in args if a.startswith("--user-data-dir=")]
        self.assertTrue(user_data_args, "No --user-data-dir argument found")
        profile_path = user_data_args[0].split("=", 1)[1]
        self.assertIn(
            "chrome_profile",
            profile_path.replace("\\", "/"),
            f"Expected 'chrome_profile' in path, got: {profile_path}"
        )

    def test_standard_flags_present(self):
        """Key stability flags must be present."""
        args = self.options._arguments
        for flag in ("--start-maximized", "--no-sandbox",
                     "--disable-dev-shm-usage", "--ignore-certificate-errors",
                     "--disable-extensions"):
            with self.subTest(flag=flag):
                self.assertIn(flag, args, f"Missing required flag: {flag}")


class TestInitBrowser(unittest.TestCase):
    """init_browser() behaviour -- patches at module level to avoid slot restrictions."""

    def _make_mock_profile_dir(self):
        """Return a MagicMock that looks enough like a Path for init_browser."""
        mock_dir = MagicMock(spec=Path)
        return mock_dir

    def test_creates_chrome_profile_dir_when_missing(self):
        """init_browser must call mkdir(parents=True, exist_ok=True) on CHROME_PROFILE_DIR."""
        mock_dir = self._make_mock_profile_dir()
        fake_driver = MagicMock()
        with patch("src.utils.chrome_utils.CHROME_PROFILE_DIR", mock_dir), \
             patch("undetected_chromedriver.Chrome", return_value=fake_driver):
            chrome_utils.init_browser()
        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_returns_driver_on_success(self):
        """init_browser must return the driver instance when Chrome succeeds."""
        mock_dir = self._make_mock_profile_dir()
        fake_driver = MagicMock()
        with patch("src.utils.chrome_utils.CHROME_PROFILE_DIR", mock_dir), \
             patch("undetected_chromedriver.Chrome", return_value=fake_driver):
            result = chrome_utils.init_browser()
        self.assertIs(result, fake_driver)

    def test_raises_runtime_error_on_driver_failure(self):
        """init_browser must raise RuntimeError when uc.Chrome raises."""
        mock_dir = self._make_mock_profile_dir()
        with patch("src.utils.chrome_utils.CHROME_PROFILE_DIR", mock_dir), \
             patch("undetected_chromedriver.Chrome",
                   side_effect=Exception("driver crash")):
            with self.assertRaises(RuntimeError) as ctx:
                chrome_utils.init_browser()
        self.assertIn("Failed to initialize browser", str(ctx.exception))

    def test_error_message_contains_original_exception(self):
        """RuntimeError message must contain the original exception text."""
        mock_dir = self._make_mock_profile_dir()
        with patch("src.utils.chrome_utils.CHROME_PROFILE_DIR", mock_dir), \
             patch("undetected_chromedriver.Chrome",
                   side_effect=Exception("session not created")):
            with self.assertRaises(RuntimeError) as ctx:
                chrome_utils.init_browser()
        self.assertIn("session not created", str(ctx.exception))


class TestModuleConstants(unittest.TestCase):
    """Module-level constant checks."""

    def test_profile_dir_is_path_instance(self):
        self.assertIsInstance(chrome_utils.CHROME_PROFILE_DIR, Path)

    def test_profile_dir_name(self):
        self.assertEqual(chrome_utils.CHROME_PROFILE_DIR.name, "chrome_profile")


class TestHTMLToPDF(unittest.TestCase):
    """HTML_to_PDF() behaviour -- uses a mock driver."""

    def _make_driver(self, pdf_data="abc123"):
        driver = MagicMock()
        driver.execute_cdp_cmd.return_value = {"data": pdf_data}
        return driver

    def test_returns_base64_data_on_success(self):
        """HTML_to_PDF returns the 'data' value from the CDP response."""
        driver = self._make_driver("pdfbase64string")
        result = chrome_utils.HTML_to_PDF("<html><body>Hi</body></html>", driver)
        self.assertEqual(result, "pdfbase64string")

    def test_calls_get_with_data_url(self):
        """driver.get must be called with a data:text/html URL."""
        driver = self._make_driver()
        chrome_utils.HTML_to_PDF("<p>test</p>", driver)
        call_arg = driver.get.call_args[0][0]
        self.assertTrue(call_arg.startswith("data:text/html;charset=utf-8,"),
                        f"Expected data URL, got: {call_arg}")

    def test_raises_value_error_on_empty_html(self):
        """HTML_to_PDF raises ValueError when html_content is empty."""
        driver = self._make_driver()
        with self.assertRaises(ValueError):
            chrome_utils.HTML_to_PDF("   ", driver)

    def test_raises_value_error_on_non_string_html(self):
        """HTML_to_PDF raises ValueError when html_content is not a string."""
        driver = self._make_driver()
        with self.assertRaises(ValueError):
            chrome_utils.HTML_to_PDF(None, driver)

    def test_raises_runtime_error_on_cdp_failure(self):
        """HTML_to_PDF raises RuntimeError when the CDP command fails."""
        driver = MagicMock()
        driver.execute_cdp_cmd.side_effect = Exception("cdp failure")
        with self.assertRaises(RuntimeError) as ctx:
            chrome_utils.HTML_to_PDF("<p>test</p>", driver)
        self.assertIn("cdp failure", str(ctx.exception))

    def test_cdp_cmd_called_with_print_to_pdf(self):
        """driver.execute_cdp_cmd must be called with 'Page.printToPDF'."""
        driver = self._make_driver()
        chrome_utils.HTML_to_PDF("<p>hi</p>", driver)
        cmd_name = driver.execute_cdp_cmd.call_args[0][0]
        self.assertEqual(cmd_name, "Page.printToPDF")


if __name__ == "__main__":
    unittest.main()
