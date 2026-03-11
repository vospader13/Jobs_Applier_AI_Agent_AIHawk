# src/ai_hawk/bot_facade.py
"""Main orchestrator for the LinkedIn Easy Apply bot.

Wires together auth, job search, and form-filling.
Enforces the 40 application/day hard cap.
Posts Discord alerts on CAPTCHA, repeated failures, session expiry, and cap hits.
"""

from typing import List

from src.ai_hawk.easy_apply_handler import EasyApplyHandler
from src.ai_hawk.job_manager import JobManager
from src.job import Job
from src.logging import logger
from src.utils.discord_reporter import send_pause_alert
from src.utils.linkedin_auth import ensure_logged_in

DAILY_CAP = 40
MAX_CONSECUTIVE_FAILURES = 3


class AIHawkBotFacade:
    """Top-level orchestrator for the LinkedIn Easy Apply automation."""

    def __init__(
        self,
        driver,
        llm_manager,
        resume_data: dict,
        job_application_profile: dict,
        daily_cap: int = DAILY_CAP,
    ):
        self.driver = driver
        self.llm_manager = llm_manager
        self.resume_data = resume_data
        self.job_application_profile = job_application_profile
        self.daily_cap = daily_cap
        self._daily_count = 0
        self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Main entry point. Logs in, searches jobs, applies up to cap."""
        ensure_logged_in(self.driver)

        job_manager = JobManager(
            driver=self.driver,
            work_preferences=self.job_application_profile,
        )
        handler = EasyApplyHandler(
            driver=self.driver,
            llm_manager=self.llm_manager,
            resume_data=self.resume_data,
        )

        jobs = job_manager.find_jobs()
        logger.info(f"Found {len(jobs)} eligible jobs")
        self._apply_to_jobs(jobs, handler)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_to_jobs(self, jobs: List[Job], handler: EasyApplyHandler = None) -> None:
        """Iterate jobs and apply, enforcing the daily cap."""
        if handler is None:
            handler = EasyApplyHandler(
                driver=self.driver,
                llm_manager=self.llm_manager,
                resume_data=self.resume_data,
            )

        for job in jobs:
            if self._daily_count >= self.daily_cap:
                logger.info(f"Daily cap of {self.daily_cap} reached. Stopping.")
                send_pause_alert(
                    reason=f"Daily application cap of {self.daily_cap} reached",
                    daily_count=self._daily_count,
                )
                break

            success = self._attempt_apply(job, handler)
            if success:
                self._daily_count += 1
                self._consecutive_failures = 0
                logger.info(
                    f"Applied ({self._daily_count}/{self.daily_cap}): "
                    f"{job.role} at {job.company}"
                )
            else:
                self._consecutive_failures += 1
                logger.warning(
                    f"Apply failed for {job.role} at {job.company}. "
                    f"Consecutive failures: {self._consecutive_failures}"
                )
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    send_pause_alert(
                        reason=f"{MAX_CONSECUTIVE_FAILURES} consecutive application failures",
                        daily_count=self._daily_count,
                    )
                    self._consecutive_failures = 0

    def _attempt_apply(self, job: Job, handler: EasyApplyHandler) -> bool:
        """Apply to a single job with error handling."""
        try:
            return handler.apply(job)
        except Exception as exc:
            logger.error(f"Unhandled error applying to {job.role}: {exc}")
            return False
