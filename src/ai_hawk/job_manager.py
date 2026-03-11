# src/ai_hawk/job_manager.py
"""LinkedIn job search manager.

Searches LinkedIn for jobs matching work_preferences.yaml criteria,
applies blacklist filters, and returns Job objects.
"""

from typing import List

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from src.job import Job
from src.logging import logger

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"
DAILY_CAP = 40


class JobManager:
    """Finds and filters LinkedIn job listings."""

    def __init__(self, driver, work_preferences: dict):
        self.driver = driver
        self.work_preferences = work_preferences
        self._company_blacklist = [
            c.lower() for c in work_preferences.get("company_blacklist", [])
        ]
        self._title_blacklist = [
            t.lower() for t in work_preferences.get("title_blacklist", [])
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_jobs(self) -> List[Job]:
        """Search LinkedIn and return a filtered list of Job objects."""
        positions = self.work_preferences.get("positions", [])
        locations = self.work_preferences.get("locations", ["Remote"])
        jobs: List[Job] = []

        for position in positions:
            for location in locations:
                try:
                    found = self._search(position, location)
                except Exception as exc:
                    logger.error(f"Search failed for {position} in {location}: {exc}")
                    found = []
                for job in found:
                    if self.is_job_allowed(job):
                        jobs.append(job)
                    if len(jobs) >= DAILY_CAP:
                        logger.info("Daily job search cap reached")
                        return jobs

        return jobs

    def is_job_allowed(self, job: Job) -> bool:
        """Return True if the job passes all blacklist filters."""
        company_lower = job.company.lower()
        role_lower = job.role.lower()

        for blocked in self._company_blacklist:
            if blocked in company_lower:
                logger.debug(f"Company blacklisted: {job.company}")
                return False

        for blocked in self._title_blacklist:
            if blocked in role_lower:
                logger.debug(f"Title blacklisted: {job.role}")
                return False

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search(self, position: str, location: str) -> List[Job]:
        """Execute a LinkedIn job search and return raw Job objects."""
        try:
            url = self._build_search_url(position, location)
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "jobs-search-results"))
            )
            return self._scrape_job_cards()
        except TimeoutException:
            logger.warning(f"Job search timed out for {position} in {location}")
            return []
        except Exception as exc:
            logger.error(f"Job search failed: {exc}")
            return []

    def _build_search_url(self, position: str, location: str) -> str:
        from urllib.parse import urlencode
        params = {
            "keywords": position,
            "location": location,
            "f_LF": "f_AL",  # Easy Apply filter
            "f_WT": "2",     # Remote
            "f_E": "4",      # Mid-Senior level
            "f_JT": "F",     # Full-time
        }
        return f"{LINKEDIN_JOBS_URL}?{urlencode(params)}"

    def _scrape_job_cards(self) -> List[Job]:
        """Parse job listing cards from the current search results page."""
        jobs = []
        try:
            cards = self.driver.find_elements(
                By.XPATH,
                "//li[contains(@class,'jobs-search-results__list-item')]"
            )
            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
        except Exception as exc:
            logger.debug(f"Card scrape error: {exc}")
        return jobs

    def _parse_card(self, card) -> Job:
        """Extract Job fields from a single result card element."""
        try:
            role = card.find_element(
                By.XPATH, ".//a[contains(@class,'job-card-list__title')]"
            ).text.strip()
            company = card.find_element(
                By.XPATH, ".//span[contains(@class,'job-card-container__primary-description')]"
            ).text.strip()
            location = ""
            try:
                location = card.find_element(
                    By.XPATH, ".//li[contains(@class,'job-card-container__metadata-item')]"
                ).text.strip()
            except NoSuchElementException:
                pass
            link = card.find_element(
                By.XPATH, ".//a[contains(@class,'job-card-list__title')]"
            ).get_attribute("href") or ""

            return Job(
                role=role,
                company=company,
                location=location,
                link=link,
                apply_method="easy_apply",
            )
        except Exception as exc:
            logger.debug(f"Could not parse job card: {exc}")
            return None
