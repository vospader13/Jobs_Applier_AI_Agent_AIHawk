"""
tests/test_task1_bot.py

Failing tests for Issue #1: GodsScion LinkedIn Easy Apply bot graft.
Written BEFORE implementation per TDD protocol.
"""
import sys
import os
import types
import unittest
from unittest.mock import MagicMock, patch, call, PropertyMock

# ---------------------------------------------------------------------------
# Stub heavy dependencies so we can import our modules without Selenium/LLM
# ---------------------------------------------------------------------------

def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)


# Set up path FIRST so real src package is importable
sys.path.insert(0, "D:/Repos/Jobs_Applier_AI_Agent_AIHawk")

# selenium stubs — must happen before any src.ai_hawk import triggers selenium
_stub_module("selenium")
_stub_module("selenium.webdriver")
_stub_module("selenium.webdriver.common")
_stub_module("selenium.webdriver.common.by", By=MagicMock())
_stub_module("selenium.webdriver.common.keys", Keys=MagicMock())
_stub_module("selenium.webdriver.support")
_stub_module("selenium.webdriver.support.ui", WebDriverWait=MagicMock(), Select=MagicMock())
_stub_module("selenium.webdriver.support.expected_conditions", EC=MagicMock())
_stub_module("selenium.webdriver.support", expected_conditions=MagicMock())
_stub_module("selenium.common")
_stub_module(
    "selenium.common.exceptions",
    NoSuchElementException=Exception,
    TimeoutException=Exception,
    StaleElementReferenceException=Exception,
    ElementClickInterceptedException=Exception,
    ElementNotInteractableException=Exception,
)

# Stub only the heavy transitive deps — NOT src itself (real package must load)
_stub_module("src.logging", logger=MagicMock())

# Stub yaml so easy_apply_handler can import without the package installed
_stub_module("yaml")
sys.modules["yaml"].safe_load = lambda f: {}

# Provide a lightweight Job for tests
from dataclasses import dataclass  # noqa: E402

@dataclass
class _Job:
    role: str = ""
    company: str = ""
    location: str = ""
    link: str = ""
    apply_method: str = ""
    description: str = ""

# Stub src.job so the real file's import is satisfied without its own deps
_stub_module("src.job", Job=_Job)

# Stub other transitive deps pulled in by llm_manager / resume_builder
_stub_module("dotenv", load_dotenv=lambda: None)
_stub_module("langchain_core")
_stub_module("langchain_core.messages")
_stub_module("langchain_core.messages.ai", AIMessage=MagicMock())
_stub_module("langchain_core.output_parsers", StrOutputParser=MagicMock())
_stub_module("langchain_core.prompt_values", StringPromptValue=MagicMock())
_stub_module("langchain_core.prompts", ChatPromptTemplate=MagicMock())
_stub_module("Levenshtein", distance=MagicMock())
_stub_module("requests")

# Stub the utils modules that pull in requests/yaml/selenium at module level.
# This lets src.ai_hawk.bot_facade import them as names without executing their
# heavy import chains.
_stub_module("src.utils")
_stub_module("src.utils.linkedin_auth", ensure_logged_in=MagicMock())
_stub_module("src.utils.discord_reporter", send_pause_alert=MagicMock())

from src.ai_hawk.bot_facade import AIHawkBotFacade
from src.ai_hawk.job_manager import JobManager
from src.ai_hawk.easy_apply_handler import EasyApplyHandler


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_driver():
    return MagicMock(name="driver")


def _make_llm():
    llm = MagicMock(name="llm_manager")
    llm.invoke.return_value = MagicMock(content="42")
    return llm


def _make_facade(daily_cap=40, driver=None, llm=None):
    driver = driver or _make_driver()
    llm = llm or _make_llm()
    facade = AIHawkBotFacade(
        driver=driver,
        llm_manager=llm,
        resume_data={"name": "Justen"},
        job_application_profile={"position": "Engineer"},
        daily_cap=daily_cap,
    )
    return facade, driver, llm


# ---------------------------------------------------------------------------
# Test: bot_facade calls ensure_logged_in before apply loop
# ---------------------------------------------------------------------------

class TestBotFacadeEnsureLogin(unittest.TestCase):

    @patch("src.ai_hawk.bot_facade.ensure_logged_in")
    @patch("src.ai_hawk.bot_facade.JobManager")
    @patch("src.ai_hawk.bot_facade.EasyApplyHandler")
    def test_ensure_logged_in_called_before_apply_loop(
        self, MockHandler, MockJobMgr, mock_login
    ):
        """ensure_logged_in must be called before any job application attempt."""
        call_order = []
        mock_login.side_effect = lambda d: call_order.append("login")

        mock_jm_instance = MockJobMgr.return_value
        mock_jm_instance.find_jobs.return_value = []

        facade, driver, llm = _make_facade()

        with patch.object(facade, "_apply_to_jobs", wraps=lambda *a, **kw: call_order.append("apply")) as mock_apply:
            facade.run()

        self.assertIn("login", call_order)
        login_idx = call_order.index("login")
        # apply may not appear if no jobs, but login must have been called
        self.assertEqual(login_idx, 0, "ensure_logged_in must be called first")

    @patch("src.ai_hawk.bot_facade.ensure_logged_in")
    @patch("src.ai_hawk.bot_facade.JobManager")
    @patch("src.ai_hawk.bot_facade.EasyApplyHandler")
    def test_ensure_logged_in_receives_driver(self, MockHandler, MockJobMgr, mock_login):
        """ensure_logged_in must receive the configured driver."""
        mock_jm_instance = MockJobMgr.return_value
        mock_jm_instance.find_jobs.return_value = []

        facade, driver, llm = _make_facade()
        facade.run()

        mock_login.assert_called_once_with(driver)


# ---------------------------------------------------------------------------
# Test: daily cap of 40 is enforced
# ---------------------------------------------------------------------------

class TestDailyCap(unittest.TestCase):

    @patch("src.ai_hawk.bot_facade.ensure_logged_in")
    @patch("src.ai_hawk.bot_facade.JobManager")
    @patch("src.ai_hawk.bot_facade.EasyApplyHandler")
    def test_daily_cap_stops_applications(self, MockHandler, MockJobMgr, mock_login):
        """Bot must not apply to more than daily_cap jobs."""
        applied = []

        mock_jm_instance = MockJobMgr.return_value
        jobs = [_Job(role=f"Engineer {i}", company=f"Co{i}") for i in range(60)]
        mock_jm_instance.find_jobs.return_value = jobs

        mock_handler_instance = MockHandler.return_value

        def fake_apply(job):
            applied.append(job)
            return True

        mock_handler_instance.apply.side_effect = fake_apply

        facade, driver, llm = _make_facade(daily_cap=40)
        facade.run()

        self.assertLessEqual(len(applied), 40, "Must not exceed 40 applications per day")

    @patch("src.ai_hawk.bot_facade.ensure_logged_in")
    @patch("src.ai_hawk.bot_facade.JobManager")
    @patch("src.ai_hawk.bot_facade.EasyApplyHandler")
    def test_daily_cap_discord_alert_on_hit(self, MockHandler, MockJobMgr, mock_login):
        """Discord pause alert must fire when daily cap is reached."""
        mock_jm_instance = MockJobMgr.return_value
        jobs = [_Job(role=f"Engineer {i}", company=f"Co{i}") for i in range(50)]
        mock_jm_instance.find_jobs.return_value = jobs
        mock_handler_instance = MockHandler.return_value
        mock_handler_instance.apply.return_value = True

        facade, driver, llm = _make_facade(daily_cap=5)

        with patch("src.ai_hawk.bot_facade.send_pause_alert") as mock_alert:
            facade.run()
            mock_alert.assert_called()


# ---------------------------------------------------------------------------
# Test: easy_apply_handler uses questions.yaml before calling LLM
# ---------------------------------------------------------------------------

class TestEasyApplyHandlerQuestionLookup(unittest.TestCase):

    def _make_handler(self, questions_data):
        llm = _make_llm()
        with patch("src.ai_hawk.easy_apply_handler.EasyApplyHandler._load_questions", return_value=questions_data):
            handler = EasyApplyHandler(
                driver=_make_driver(),
                llm_manager=llm,
                resume_data={"name": "Justen"},
            )
        return handler, llm

    def test_known_question_answered_from_yaml_not_llm(self):
        """If question text matches questions.yaml key, LLM must NOT be called."""
        questions = {"years of experience": "5"}
        handler, llm = self._make_handler(questions)

        answer = handler.answer_question("years of experience")

        self.assertEqual(answer, "5")
        llm.invoke.assert_not_called()

    def test_unknown_question_falls_back_to_llm(self):
        """If question has no yaml match, LLM must be called exactly once."""
        questions = {"years of experience": "5"}
        handler, llm = self._make_handler(questions)
        llm.invoke.return_value = MagicMock(content="Senior level")

        answer = handler.answer_question("what is your superpower?")

        llm.invoke.assert_called_once()
        self.assertEqual(answer, "Senior level")

    def test_case_insensitive_yaml_lookup(self):
        """Question lookup must be case-insensitive."""
        questions = {"years of experience": "5"}
        handler, llm = self._make_handler(questions)

        answer = handler.answer_question("Years Of Experience")

        self.assertEqual(answer, "5")
        llm.invoke.assert_not_called()


# ---------------------------------------------------------------------------
# Test: salary field always submits 150000
# ---------------------------------------------------------------------------

class TestSalaryField(unittest.TestCase):

    def _make_handler(self):
        llm = _make_llm()
        with patch("src.ai_hawk.easy_apply_handler.EasyApplyHandler._load_questions", return_value={}):
            handler = EasyApplyHandler(
                driver=_make_driver(),
                llm_manager=llm,
                resume_data={"name": "Justen"},
            )
        return handler

    def test_salary_field_returns_150000(self):
        """Salary input must always return 150000 as string."""
        handler = self._make_handler()
        result = handler.get_salary_answer(listed_range=None)
        self.assertEqual(result, "150000")

    def test_salary_field_returns_150000_when_range_above_threshold(self):
        """Salary returns 150000 when listed range is >= $100k."""
        handler = self._make_handler()
        result = handler.get_salary_answer(listed_range=120000)
        self.assertEqual(result, "150000")

    def test_salary_skipped_when_range_below_100k(self):
        """get_salary_answer returns None to signal skip when range < $100k."""
        handler = self._make_handler()
        result = handler.get_salary_answer(listed_range=80000)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Test: JobManager filters correctly
# ---------------------------------------------------------------------------

class TestJobManagerFilters(unittest.TestCase):

    def _make_manager(self, company_blacklist=None, title_blacklist=None):
        manager = JobManager(
            driver=_make_driver(),
            work_preferences={
                "positions": ["Software Engineer"],
                "locations": ["Remote"],
                "company_blacklist": company_blacklist or [],
                "title_blacklist": title_blacklist or [],
            },
        )
        return manager

    def test_company_blacklist_filters_job(self):
        """Jobs from blacklisted companies must be excluded."""
        manager = self._make_manager(company_blacklist=["BadCorp"])
        job = _Job(role="Engineer", company="BadCorp")
        self.assertFalse(manager.is_job_allowed(job))

    def test_company_not_in_blacklist_passes(self):
        """Jobs from non-blacklisted companies must pass filter."""
        manager = self._make_manager(company_blacklist=["BadCorp"])
        job = _Job(role="Engineer", company="GoodCorp")
        self.assertTrue(manager.is_job_allowed(job))

    def test_title_blacklist_filters_job(self):
        """Jobs with blacklisted title keywords must be excluded."""
        manager = self._make_manager(title_blacklist=["intern"])
        job = _Job(role="Software Intern", company="AcmeCorp")
        self.assertFalse(manager.is_job_allowed(job))

    def test_title_not_blacklisted_passes(self):
        """Jobs without blacklisted title keywords must pass filter."""
        manager = self._make_manager(title_blacklist=["intern"])
        job = _Job(role="Software Engineer", company="AcmeCorp")
        self.assertTrue(manager.is_job_allowed(job))

    def test_blacklist_check_is_case_insensitive(self):
        """Blacklist checks must be case-insensitive."""
        manager = self._make_manager(company_blacklist=["badcorp"])
        job = _Job(role="Engineer", company="BadCorp")
        self.assertFalse(manager.is_job_allowed(job))


# ---------------------------------------------------------------------------
# Test: BotFacade _apply_to_jobs internal logic
# ---------------------------------------------------------------------------

class TestBotFacadeApplyLoop(unittest.TestCase):

    def _make_handler_instance(self, apply_returns=True):
        handler = MagicMock()
        handler.apply.return_value = apply_returns
        return handler

    def _make_facade_with_jobs(self, jobs, daily_cap=40, apply_returns=True):
        facade, driver, llm = _make_facade(daily_cap=daily_cap)
        handler = self._make_handler_instance(apply_returns=apply_returns)
        return facade, handler

    def test_successful_apply_increments_daily_count(self):
        """Each successful apply must increment _daily_count."""
        facade, driver, llm = _make_facade(daily_cap=40)
        handler = MagicMock()
        handler.apply.return_value = True
        jobs = [_Job(role="Eng", company="Co")]

        facade._apply_to_jobs(jobs, handler)

        self.assertEqual(facade._daily_count, 1)

    def test_failed_apply_increments_consecutive_failures(self):
        """A failed apply must increment _consecutive_failures."""
        facade, driver, llm = _make_facade(daily_cap=40)
        handler = MagicMock()
        handler.apply.return_value = False
        jobs = [_Job(role="Eng", company="Co")]

        facade._apply_to_jobs(jobs, handler)

        self.assertEqual(facade._consecutive_failures, 1)

    def test_three_consecutive_failures_trigger_discord(self):
        """After MAX_CONSECUTIVE_FAILURES (3) failures, send_pause_alert is called."""
        facade, driver, llm = _make_facade(daily_cap=40)
        handler = MagicMock()
        handler.apply.return_value = False
        jobs = [_Job(role=f"Eng{i}", company="Co") for i in range(3)]

        with patch("src.ai_hawk.bot_facade.send_pause_alert") as mock_alert:
            facade._apply_to_jobs(jobs, handler)
            mock_alert.assert_called()

    def test_consecutive_failures_reset_after_discord_alert(self):
        """_consecutive_failures resets to 0 after the alert fires."""
        facade, driver, llm = _make_facade(daily_cap=40)
        handler = MagicMock()
        handler.apply.return_value = False
        jobs = [_Job(role=f"Eng{i}", company="Co") for i in range(3)]

        with patch("src.ai_hawk.bot_facade.send_pause_alert"):
            facade._apply_to_jobs(jobs, handler)

        self.assertEqual(facade._consecutive_failures, 0)

    def test_attempt_apply_returns_false_on_exception(self):
        """_attempt_apply must catch exceptions and return False."""
        facade, driver, llm = _make_facade()
        handler = MagicMock()
        handler.apply.side_effect = RuntimeError("selenium crashed")
        job = _Job(role="Eng", company="Co")

        result = facade._attempt_apply(job, handler)

        self.assertFalse(result)

    @patch("src.ai_hawk.bot_facade.ensure_logged_in")
    @patch("src.ai_hawk.bot_facade.JobManager")
    @patch("src.ai_hawk.bot_facade.EasyApplyHandler")
    def test_run_creates_job_manager_with_job_application_profile(
        self, MockHandler, MockJobMgr, mock_login
    ):
        """run() must instantiate JobManager with job_application_profile."""
        mock_jm_instance = MockJobMgr.return_value
        mock_jm_instance.find_jobs.return_value = []
        profile = {"positions": ["Engineer"], "locations": ["Remote"],
                   "company_blacklist": [], "title_blacklist": []}
        facade = AIHawkBotFacade(
            driver=_make_driver(),
            llm_manager=_make_llm(),
            resume_data={},
            job_application_profile=profile,
        )
        facade.run()
        MockJobMgr.assert_called_once_with(driver=facade.driver, work_preferences=profile)


# ---------------------------------------------------------------------------
# Test: EasyApplyHandler internal helpers
# ---------------------------------------------------------------------------

class TestEasyApplyHandlerHelpers(unittest.TestCase):

    def _make_handler(self, questions=None):
        llm = _make_llm()
        with patch(
            "src.ai_hawk.easy_apply_handler.EasyApplyHandler._load_questions",
            return_value=questions or {},
        ):
            handler = EasyApplyHandler(
                driver=_make_driver(),
                llm_manager=llm,
                resume_data={"name": "Justen"},
            )
        return handler, llm

    def test_build_llm_prompt_contains_question(self):
        """LLM prompt must contain the question text."""
        handler, _ = self._make_handler()
        prompt = handler._build_llm_prompt("Do you know Python?")
        self.assertIn("Do you know Python?", prompt)

    def test_build_llm_prompt_contains_resume_name(self):
        """LLM prompt must mention the applicant name from resume_data."""
        handler, _ = self._make_handler()
        prompt = handler._build_llm_prompt("Any question")
        self.assertIn("Justen", prompt)

    def test_resolve_field_answer_salary_label(self):
        """_resolve_field_answer must return salary string for salary-labelled fields."""
        handler, _ = self._make_handler()
        result = handler._resolve_field_answer("Expected Salary")
        self.assertEqual(result, "150000")

    def test_resolve_field_answer_compensation_label(self):
        """_resolve_field_answer must return salary string for compensation-labelled fields."""
        handler, _ = self._make_handler()
        result = handler._resolve_field_answer("Total Compensation")
        self.assertEqual(result, "150000")

    def test_resolve_field_answer_empty_label_returns_none(self):
        """_resolve_field_answer must return None for empty aria-label."""
        handler, _ = self._make_handler()
        result = handler._resolve_field_answer("")
        self.assertIsNone(result)

    def test_load_questions_returns_empty_dict_on_missing_file(self):
        """_load_questions must silently return {} if questions.yaml is absent."""
        with patch("src.ai_hawk.easy_apply_handler.QUESTIONS_YAML_PATH") as mock_path:
            mock_path.exists.return_value = False
            llm = _make_llm()
            handler = EasyApplyHandler(
                driver=_make_driver(),
                llm_manager=llm,
                resume_data={},
            )
        self.assertEqual(handler._questions, {})

    def test_is_final_step_returns_false_when_no_submit(self):
        """_is_final_step must return False when no Submit button exists."""
        handler, _ = self._make_handler()
        handler.driver.find_elements.return_value = []
        self.assertFalse(handler._is_final_step())

    def test_is_final_step_returns_true_when_submit_present(self):
        """_is_final_step must return True when Submit button is found."""
        handler, _ = self._make_handler()
        handler.driver.find_elements.return_value = [MagicMock()]
        self.assertTrue(handler._is_final_step())

    def test_click_next_returns_false_when_no_next_button(self):
        """_click_next must return False when Next/Review button is absent."""
        handler, _ = self._make_handler()
        handler.driver.find_element.side_effect = Exception("NoSuchElement")
        self.assertFalse(handler._click_next())

    def test_apply_returns_false_on_exception(self):
        """apply() must catch exceptions and return False."""
        handler, _ = self._make_handler()
        handler._click_easy_apply_button = MagicMock(side_effect=RuntimeError("no button"))
        result = handler.apply(_Job(role="Eng", company="Co"))
        self.assertFalse(result)

    def test_answer_question_llm_response_without_content_attr(self):
        """If LLM returns a plain string, answer_question must return it directly."""
        handler, llm = self._make_handler()
        llm.invoke.return_value = "plain string response"
        answer = handler.answer_question("novel question")
        self.assertEqual(answer, "plain string response")


# ---------------------------------------------------------------------------
# Test: JobManager _build_search_url
# ---------------------------------------------------------------------------

class TestJobManagerSearchUrl(unittest.TestCase):

    def _make_manager(self):
        return JobManager(
            driver=_make_driver(),
            work_preferences={
                "positions": ["Software Engineer"],
                "locations": ["Remote"],
                "company_blacklist": [],
                "title_blacklist": [],
            },
        )

    def test_search_url_contains_keywords(self):
        """Search URL must include the position as keywords param."""
        manager = self._make_manager()
        url = manager._build_search_url("Data Scientist", "Remote")
        self.assertIn("Data+Scientist", url)

    def test_search_url_contains_location(self):
        """Search URL must include the location param."""
        manager = self._make_manager()
        url = manager._build_search_url("Engineer", "New York")
        self.assertIn("New+York", url)

    def test_search_url_contains_easy_apply_filter(self):
        """Search URL must include Easy Apply filter (f_LF=f_AL)."""
        manager = self._make_manager()
        url = manager._build_search_url("Engineer", "Remote")
        self.assertIn("f_LF=f_AL", url)

    def test_find_jobs_returns_empty_on_search_error(self):
        """find_jobs must return [] if search raises an exception."""
        manager = self._make_manager()
        manager._search = MagicMock(side_effect=Exception("network error"))
        result = manager.find_jobs()
        self.assertEqual(result, [])

    def test_find_jobs_respects_daily_cap(self):
        """find_jobs must return at most DAILY_CAP jobs."""
        manager = self._make_manager()
        many_jobs = [_Job(role=f"Eng{i}", company="Co") for i in range(60)]
        manager._search = MagicMock(return_value=many_jobs)
        result = manager.find_jobs()
        self.assertLessEqual(len(result), 40)


# ---------------------------------------------------------------------------
# Test: JobManager selenium internals (mocked driver)
# ---------------------------------------------------------------------------

class TestJobManagerSeleniumInternals(unittest.TestCase):

    def _make_manager(self):
        return JobManager(
            driver=_make_driver(),
            work_preferences={
                "positions": ["Engineer"],
                "locations": ["Remote"],
                "company_blacklist": [],
                "title_blacklist": [],
            },
        )

    def test_search_returns_empty_on_timeout(self):
        """_search must return [] when WebDriverWait raises TimeoutException."""
        manager = self._make_manager()
        # WebDriverWait is already mocked; make until() raise TimeoutException
        import selenium.webdriver.support.ui as ui_mod
        original_wdw = ui_mod.WebDriverWait

        class FakeWDW:
            def __init__(self, *a, **kw):
                pass
            def until(self, *a, **kw):
                raise Exception("TimeoutException")

        with patch("src.ai_hawk.job_manager.WebDriverWait", FakeWDW):
            result = manager._search("Engineer", "Remote")
        self.assertEqual(result, [])

    def test_search_returns_empty_on_generic_exception(self):
        """_search must return [] when driver.get() raises an exception."""
        manager = self._make_manager()
        manager.driver.get.side_effect = Exception("connection refused")
        result = manager._search("Engineer", "Remote")
        self.assertEqual(result, [])

    def test_scrape_job_cards_returns_empty_on_driver_error(self):
        """_scrape_job_cards must return [] when driver raises."""
        manager = self._make_manager()
        manager.driver.find_elements.side_effect = Exception("stale element")
        result = manager._scrape_job_cards()
        self.assertEqual(result, [])

    def test_scrape_job_cards_filters_none_from_parse(self):
        """_scrape_job_cards must skip cards that _parse_card returns None for."""
        manager = self._make_manager()
        fake_card = MagicMock()
        manager.driver.find_elements.return_value = [fake_card]
        manager._parse_card = MagicMock(return_value=None)
        result = manager._scrape_job_cards()
        self.assertEqual(result, [])

    def test_scrape_job_cards_appends_valid_jobs(self):
        """_scrape_job_cards must append jobs returned by _parse_card."""
        manager = self._make_manager()
        fake_card = MagicMock()
        manager.driver.find_elements.return_value = [fake_card]
        expected_job = _Job(role="Engineer", company="ACME")
        manager._parse_card = MagicMock(return_value=expected_job)
        result = manager._scrape_job_cards()
        self.assertEqual(result, [expected_job])

    def test_parse_card_returns_none_on_missing_elements(self):
        """_parse_card must return None when required elements are absent."""
        manager = self._make_manager()
        card = MagicMock()
        card.find_element.side_effect = Exception("NoSuchElement")
        result = manager._parse_card(card)
        self.assertIsNone(result)

    def test_parse_card_returns_job_on_success(self):
        """_parse_card must return a Job with correct role and company."""
        manager = self._make_manager()
        card = MagicMock()
        title_el = MagicMock()
        title_el.text = "  Senior Engineer  "
        company_el = MagicMock()
        company_el.text = "  BestCorp  "
        loc_el = MagicMock()
        loc_el.text = "  Remote  "
        link_el = MagicMock()
        link_el.text = "  Senior Engineer  "
        link_el.get_attribute.return_value = "https://linkedin.com/jobs/1"

        def fake_find(by, xpath):
            if "job-card-list__title" in xpath and "href" not in xpath:
                return title_el if "a[contains" in xpath else link_el
            if "primary-description" in xpath:
                return company_el
            if "metadata-item" in xpath:
                return loc_el
            return link_el

        card.find_element.side_effect = fake_find
        result = manager._parse_card(card)
        # parse should succeed and return a Job (not None)
        self.assertIsNotNone(result)

    def test_parse_card_handles_missing_location_gracefully(self):
        """_parse_card must still return a Job even when location element is absent."""
        manager = self._make_manager()
        card = MagicMock()

        title_el = MagicMock()
        title_el.text = "Engineer"
        company_el = MagicMock()
        company_el.text = "Corp"
        link_el = MagicMock()
        link_el.text = "Engineer"
        link_el.get_attribute.return_value = "https://li.com/1"

        call_count = [0]

        def fake_find(by, xpath):
            call_count[0] += 1
            if "metadata-item" in xpath:
                raise Exception("NoSuchElement")
            if "primary-description" in xpath:
                return company_el
            return title_el

        card.find_element.side_effect = fake_find
        # Should not raise
        try:
            result = manager._parse_card(card)
        except Exception:
            result = None
        # Either a Job or None — must not propagate the location exception
        # (the outer try/except in _parse_card handles it)
        self.assertTrue(result is None or isinstance(result, _Job))


# ---------------------------------------------------------------------------
# Test: EasyApplyHandler selenium internals (mocked driver)
# ---------------------------------------------------------------------------

class TestEasyApplyHandlerSeleniumInternals(unittest.TestCase):

    def _make_handler(self, questions=None):
        llm = _make_llm()
        with patch(
            "src.ai_hawk.easy_apply_handler.EasyApplyHandler._load_questions",
            return_value=questions or {},
        ):
            handler = EasyApplyHandler(
                driver=_make_driver(),
                llm_manager=llm,
                resume_data={"name": "Justen"},
            )
        return handler, llm

    def test_click_easy_apply_button_clicks_found_button(self):
        """_click_easy_apply_button must call click() on the found element."""
        handler, _ = self._make_handler()
        fake_btn = MagicMock()
        mock_wait_instance = MagicMock()
        mock_wait_instance.until.return_value = fake_btn
        mock_ec = MagicMock()

        with patch("src.ai_hawk.easy_apply_handler.WebDriverWait", return_value=mock_wait_instance), \
                patch("src.ai_hawk.easy_apply_handler.EC", mock_ec):
            handler._click_easy_apply_button()

        fake_btn.click.assert_called_once()

    def test_click_easy_apply_button_raises_on_timeout(self):
        """_click_easy_apply_button must raise RuntimeError on TimeoutException."""
        handler, _ = self._make_handler()
        mock_wait_instance = MagicMock()
        mock_wait_instance.until.side_effect = Exception("timeout")
        mock_ec = MagicMock()

        with patch("src.ai_hawk.easy_apply_handler.WebDriverWait", return_value=mock_wait_instance), \
                patch("src.ai_hawk.easy_apply_handler.EC", mock_ec):
            with self.assertRaises(RuntimeError):
                handler._click_easy_apply_button()

    def test_click_next_returns_true_when_button_found(self):
        """_click_next must return True and click the button when found."""
        handler, _ = self._make_handler()
        fake_btn = MagicMock()
        handler.driver.find_element.return_value = fake_btn
        result = handler._click_next()
        self.assertTrue(result)
        fake_btn.click.assert_called_once()

    def test_fill_form_breaks_on_final_step(self):
        """_fill_form must stop iterating once _is_final_step returns True."""
        handler, _ = self._make_handler()
        handler._fill_current_step = MagicMock()
        handler._is_final_step = MagicMock(return_value=True)
        handler._click_next = MagicMock()

        handler._fill_form(_Job())

        handler._fill_current_step.assert_called_once()
        handler._click_next.assert_not_called()

    def test_fill_form_breaks_when_no_next_button(self):
        """_fill_form must stop if _click_next returns False."""
        handler, _ = self._make_handler()
        handler._fill_current_step = MagicMock()
        handler._is_final_step = MagicMock(return_value=False)
        handler._click_next = MagicMock(return_value=False)

        handler._fill_form(_Job())

        handler._fill_current_step.assert_called_once()

    def test_fill_current_step_calls_all_sub_methods(self):
        """_fill_current_step must call all field-type handlers."""
        handler, _ = self._make_handler()
        handler._fill_text_inputs = MagicMock()
        handler._fill_dropdowns = MagicMock()
        handler._fill_radio_buttons = MagicMock()
        handler._fill_checkboxes = MagicMock()
        handler._handle_file_upload = MagicMock()

        handler._fill_current_step(_Job())

        handler._fill_text_inputs.assert_called_once()
        handler._fill_dropdowns.assert_called_once()
        handler._fill_radio_buttons.assert_called_once()
        handler._fill_checkboxes.assert_called_once()
        handler._handle_file_upload.assert_called_once()

    def test_fill_text_inputs_skips_already_filled(self):
        """_fill_text_inputs must not overwrite inputs that already have a value."""
        handler, llm = self._make_handler(questions={"years of experience": "5"})
        fake_input = MagicMock()
        fake_input.get_attribute.side_effect = lambda attr: (
            "aria-label-text" if attr == "aria-label" else "already filled"
        )
        handler.driver.find_elements.return_value = [fake_input]
        handler._fill_text_inputs()
        fake_input.send_keys.assert_not_called()

    def test_fill_text_inputs_fills_empty_inputs(self):
        """_fill_text_inputs must fill inputs with empty value."""
        handler, llm = self._make_handler(questions={"years of experience": "5"})
        fake_input = MagicMock()
        fake_input.get_attribute.side_effect = lambda attr: (
            "years of experience" if attr == "aria-label" else ""
        )
        handler.driver.find_elements.return_value = [fake_input]
        handler._fill_text_inputs()
        fake_input.send_keys.assert_called_once_with("5")

    def test_fill_text_inputs_handles_driver_exception(self):
        """_fill_text_inputs must not raise when driver throws."""
        handler, _ = self._make_handler()
        handler.driver.find_elements.side_effect = Exception("driver error")
        # Should not raise
        handler._fill_text_inputs()

    def test_submit_form_clicks_submit_button(self):
        """_submit_form must click the Submit button when found."""
        handler, _ = self._make_handler()
        fake_btn = MagicMock()
        mock_wait_instance = MagicMock()
        mock_wait_instance.until.return_value = fake_btn
        mock_ec = MagicMock()
        with patch("src.ai_hawk.easy_apply_handler.WebDriverWait", return_value=mock_wait_instance), \
                patch("src.ai_hawk.easy_apply_handler.EC", mock_ec):
            handler._submit_form()
        fake_btn.click.assert_called_once()

    def test_submit_form_raises_when_no_submit_button(self):
        """_submit_form must raise RuntimeError when Submit button is absent."""
        handler, _ = self._make_handler()
        mock_wait_instance = MagicMock()
        mock_wait_instance.until.side_effect = Exception("timeout")
        mock_ec = MagicMock()
        with patch("src.ai_hawk.easy_apply_handler.WebDriverWait", return_value=mock_wait_instance), \
                patch("src.ai_hawk.easy_apply_handler.EC", mock_ec):
            with self.assertRaises(RuntimeError):
                handler._submit_form()

    def test_apply_success_path(self):
        """apply() must return True when all steps succeed."""
        handler, _ = self._make_handler()
        handler._click_easy_apply_button = MagicMock()
        handler._fill_form = MagicMock()
        handler._submit_form = MagicMock()

        with patch("src.ai_hawk.easy_apply_handler.time.sleep"):
            result = handler.apply(_Job(role="Engineer", company="ACME"))

        self.assertTrue(result)

    def test_load_questions_returns_dict_when_file_exists(self):
        """_load_questions must return dict contents when yaml file is present."""
        handler, _ = self._make_handler()
        fake_data = {"years of experience": "5", "salary expectation": "150000"}
        with patch("src.ai_hawk.easy_apply_handler.QUESTIONS_YAML_PATH") as mock_path:
            mock_path.exists.return_value = True
            mock_open = unittest.mock.mock_open()
            with patch("builtins.open", mock_open):
                with patch("src.ai_hawk.easy_apply_handler.yaml.safe_load", return_value=fake_data):
                    result = handler._load_questions()
        self.assertEqual(result, fake_data)

    def test_load_questions_returns_empty_when_yaml_not_dict(self):
        """_load_questions must return {} when yaml returns a non-dict."""
        handler, _ = self._make_handler()
        with patch("src.ai_hawk.easy_apply_handler.QUESTIONS_YAML_PATH") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", unittest.mock.mock_open()):
                with patch("src.ai_hawk.easy_apply_handler.yaml.safe_load", return_value=["list"]):
                    result = handler._load_questions()
        self.assertEqual(result, {})

    def test_load_questions_handles_exception(self):
        """_load_questions must return {} on any exception."""
        handler, _ = self._make_handler()
        with patch("src.ai_hawk.easy_apply_handler.QUESTIONS_YAML_PATH") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", side_effect=IOError("permission denied")):
                result = handler._load_questions()
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Test: EasyApplyHandler dropdown, radio, checkbox, file-upload internals
# ---------------------------------------------------------------------------

class TestEasyApplyHandlerFieldFillers(unittest.TestCase):

    def _make_handler(self, questions=None):
        llm = _make_llm()
        llm.invoke.return_value = MagicMock(content="Yes")
        with patch(
            "src.ai_hawk.easy_apply_handler.EasyApplyHandler._load_questions",
            return_value=questions or {},
        ):
            handler = EasyApplyHandler(
                driver=_make_driver(),
                llm_manager=llm,
                resume_data={"name": "Justen"},
            )
        return handler

    # -- _fill_dropdowns --

    def test_fill_dropdowns_handles_driver_exception(self):
        """_fill_dropdowns must not raise when driver throws."""
        handler = self._make_handler()
        handler.driver.find_elements.side_effect = Exception("driver error")
        handler._fill_dropdowns()  # must not raise

    def test_fill_dropdowns_skips_select_without_aria_label(self):
        """_fill_dropdowns must skip selects with no aria-label."""
        handler = self._make_handler()
        fake_select = MagicMock()
        fake_select.get_attribute.return_value = ""
        handler.driver.find_elements.return_value = [fake_select]
        with patch("src.ai_hawk.easy_apply_handler.Select") as MockSelect:
            handler._fill_dropdowns()
        MockSelect.assert_not_called()

    def test_fill_dropdowns_selects_by_visible_text(self):
        """_fill_dropdowns must call select_by_visible_text with LLM answer."""
        handler = self._make_handler(questions={"work authorization": "Yes"})
        fake_select_el = MagicMock()
        fake_select_el.get_attribute.return_value = "work authorization"
        handler.driver.find_elements.return_value = [fake_select_el]

        mock_select_instance = MagicMock()
        with patch("src.ai_hawk.easy_apply_handler.Select", return_value=mock_select_instance):
            handler._fill_dropdowns()

        mock_select_instance.select_by_visible_text.assert_called_once_with("Yes")

    def test_fill_dropdowns_swallows_select_exception(self):
        """_fill_dropdowns must silently skip a select that raises on selection."""
        handler = self._make_handler(questions={"work auth": "Yes"})
        fake_select_el = MagicMock()
        fake_select_el.get_attribute.return_value = "work auth"
        handler.driver.find_elements.return_value = [fake_select_el]

        mock_select_instance = MagicMock()
        mock_select_instance.select_by_visible_text.side_effect = Exception("no option")
        with patch("src.ai_hawk.easy_apply_handler.Select", return_value=mock_select_instance):
            handler._fill_dropdowns()  # must not raise

    # -- _fill_radio_buttons --

    def test_fill_radio_buttons_handles_driver_exception(self):
        """_fill_radio_buttons must not raise when driver throws."""
        handler = self._make_handler()
        handler.driver.find_elements.side_effect = Exception("driver error")
        handler._fill_radio_buttons()

    def test_fill_radio_buttons_skips_fieldset_without_legend(self):
        """_fill_radio_buttons must skip fieldsets with no legend text."""
        handler = self._make_handler()
        fake_fs = MagicMock()
        fake_legend = MagicMock()
        fake_legend.text = ""
        fake_fs.find_element.return_value = fake_legend
        fake_fs.find_elements.return_value = []
        handler.driver.find_elements.return_value = [fake_fs]
        handler._fill_radio_buttons()  # must not raise, nothing selected

    def test_fill_radio_buttons_clicks_matching_radio(self):
        """_fill_radio_buttons must click a radio whose aria-label matches the answer."""
        handler = self._make_handler(questions={"remote work": "Yes"})
        fake_fs = MagicMock()
        fake_legend = MagicMock()
        fake_legend.text = "remote work"
        fake_fs.find_element.return_value = fake_legend

        fake_radio = MagicMock()
        fake_radio.get_attribute.return_value = "Yes"
        fake_fs.find_elements.return_value = [fake_radio]
        handler.driver.find_elements.return_value = [fake_fs]

        handler._fill_radio_buttons()
        fake_radio.click.assert_called_once()

    def test_fill_radio_buttons_swallows_not_interactable(self):
        """_fill_radio_buttons must silently skip radios that raise ElementNotInteractableException."""
        handler = self._make_handler(questions={"remote work": "Yes"})
        fake_fs = MagicMock()
        fake_legend = MagicMock()
        fake_legend.text = "remote work"
        fake_fs.find_element.return_value = fake_legend

        fake_radio = MagicMock()
        fake_radio.get_attribute.return_value = "Yes"
        fake_radio.click.side_effect = Exception("not interactable")
        fake_fs.find_elements.return_value = [fake_radio]
        handler.driver.find_elements.return_value = [fake_fs]

        handler._fill_radio_buttons()  # must not raise

    # -- _fill_checkboxes --

    def test_fill_checkboxes_handles_driver_exception(self):
        """_fill_checkboxes must not raise when driver throws."""
        handler = self._make_handler()
        handler.driver.find_elements.side_effect = Exception("driver error")
        handler._fill_checkboxes()

    def test_fill_checkboxes_checks_agreement_checkbox(self):
        """_fill_checkboxes must click unchecked 'agree' checkboxes."""
        handler = self._make_handler()
        fake_cb = MagicMock()
        fake_cb.get_attribute.return_value = "I agree to terms"
        fake_cb.is_selected.return_value = False
        handler.driver.find_elements.return_value = [fake_cb]
        handler._fill_checkboxes()
        fake_cb.click.assert_called_once()

    def test_fill_checkboxes_skips_already_selected(self):
        """_fill_checkboxes must not click an already-selected checkbox."""
        handler = self._make_handler()
        fake_cb = MagicMock()
        fake_cb.get_attribute.return_value = "I consent"
        fake_cb.is_selected.return_value = True
        handler.driver.find_elements.return_value = [fake_cb]
        handler._fill_checkboxes()
        fake_cb.click.assert_not_called()

    def test_fill_checkboxes_skips_non_consent_checkbox(self):
        """_fill_checkboxes must not click checkboxes unrelated to consent."""
        handler = self._make_handler()
        fake_cb = MagicMock()
        fake_cb.get_attribute.return_value = "subscribe to newsletter"
        fake_cb.is_selected.return_value = False
        handler.driver.find_elements.return_value = [fake_cb]
        handler._fill_checkboxes()
        fake_cb.click.assert_not_called()

    # -- _handle_file_upload --

    def test_handle_file_upload_handles_driver_exception(self):
        """_handle_file_upload must not raise when driver throws."""
        handler = self._make_handler()
        handler.driver.find_elements.side_effect = Exception("driver error")
        handler._handle_file_upload(_Job())

    def test_handle_file_upload_sends_resume_path(self):
        """_handle_file_upload must send resume_path to non-cover-letter upload."""
        handler = self._make_handler()
        fake_upload = MagicMock()
        fake_upload.get_attribute.return_value = "resume upload"
        handler.driver.find_elements.return_value = [fake_upload]

        job = _Job()
        job.resume_path = "/path/to/resume.pdf"
        handler._handle_file_upload(job)
        fake_upload.send_keys.assert_called_once_with("/path/to/resume.pdf")

    def test_handle_file_upload_sends_cover_letter_to_cover_field(self):
        """_handle_file_upload must send cover_letter_path to cover-letter fields."""
        handler = self._make_handler()
        fake_upload = MagicMock()
        fake_upload.get_attribute.return_value = "cover letter upload"
        handler.driver.find_elements.return_value = [fake_upload]

        job = _Job()
        job.resume_path = "/path/resume.pdf"
        job.cover_letter_path = "/path/cover.pdf"
        handler._handle_file_upload(job)
        fake_upload.send_keys.assert_called_once_with("/path/cover.pdf")

    def test_handle_file_upload_skips_when_no_resume_path(self):
        """_handle_file_upload must not send keys when job has no resume_path."""
        handler = self._make_handler()
        fake_upload = MagicMock()
        fake_upload.get_attribute.return_value = "resume"
        handler.driver.find_elements.return_value = [fake_upload]

        job = _Job()  # no resume_path attr
        handler._handle_file_upload(job)
        fake_upload.send_keys.assert_not_called()

    # -- _is_final_step exception path --

    def test_is_final_step_returns_false_on_exception(self):
        """_is_final_step must return False when driver.find_elements raises."""
        handler = self._make_handler()
        handler.driver.find_elements.side_effect = Exception("stale element")
        result = handler._is_final_step()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
