# src/ai_hawk/easy_apply_handler.py
"""LinkedIn Easy Apply form handler.

Handles all field types in the Easy Apply modal.
Uses aria-label + text content matching — NOT CSS class selectors,
which rot when LinkedIn updates their front-end.
"""

import random
import time
from pathlib import Path
from typing import Optional

import yaml
from selenium.common.exceptions import (
    ElementNotInteractableException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from src.logging import logger

SALARY_DEFAULT = 150000
SALARY_SKIP_THRESHOLD = 100000
QUESTIONS_YAML_PATH = Path("data_folder/questions.yaml")
DELAY_MIN = 45
DELAY_MAX = 120


class EasyApplyHandler:
    """Fills and submits LinkedIn Easy Apply forms."""

    def __init__(self, driver, llm_manager, resume_data: dict):
        self.driver = driver
        self.llm_manager = llm_manager
        self.resume_data = resume_data
        self._questions = self._load_questions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, job) -> bool:
        """Attempt to apply to a single job via Easy Apply modal.

        Returns True on success, False on failure.
        """
        logger.info(f"Applying to {job.role} at {job.company}")
        try:
            self._click_easy_apply_button()
            self._fill_form(job)
            self._submit_form()
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            logger.debug(f"Waiting {delay:.1f}s before next application")
            time.sleep(delay)
            return True
        except Exception as exc:
            logger.error(f"Easy apply failed for {job.role}: {exc}")
            return False

    def answer_question(self, question_text: str) -> str:
        """Return an answer for a screening question.

        Lookup order:
        1. questions.yaml (case-insensitive key match)
        2. LLM via ClaudeExecutorModel
        """
        key = question_text.strip().lower()
        for yaml_key, yaml_answer in self._questions.items():
            if yaml_key.strip().lower() == key:
                logger.debug(f"Question answered from yaml: {question_text!r}")
                return str(yaml_answer)

        logger.debug(f"Question not in yaml, asking LLM: {question_text!r}")
        prompt = self._build_llm_prompt(question_text)
        response = self.llm_manager.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    def get_salary_answer(self, listed_range: Optional[int]) -> Optional[str]:
        """Return the salary string to submit, or None to skip the field.

        Rules:
        - If listed_range is set and < $100k: return None (skip field)
        - Otherwise: always return "150000"
        """
        if listed_range is not None and listed_range < SALARY_SKIP_THRESHOLD:
            logger.debug(f"Salary range {listed_range} < threshold — skipping field")
            return None
        return str(SALARY_DEFAULT)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_questions(self) -> dict:
        """Load questions.yaml from data_folder. Returns empty dict on failure."""
        try:
            if QUESTIONS_YAML_PATH.exists():
                with open(QUESTIONS_YAML_PATH, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning(f"Could not load questions.yaml: {exc}")
        return {}

    def _build_llm_prompt(self, question_text: str) -> str:
        name = self.resume_data.get("name", "the applicant")
        return (
            f"You are answering a LinkedIn job application screening question "
            f"on behalf of {name}.\n\n"
            f"Question: {question_text}\n\n"
            f"Provide a concise, professional answer in 1-3 sentences."
        )

    def _click_easy_apply_button(self) -> None:
        """Find and click the Easy Apply button by aria-label."""
        try:
            wait = WebDriverWait(self.driver, 10)
            btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@aria-label,'Easy Apply')]")
                )
            )
            btn.click()
        except TimeoutException:
            raise RuntimeError("Easy Apply button not found or not clickable")

    def _fill_form(self, job) -> None:
        """Iterate through form steps, filling fields."""
        max_steps = 10
        for step in range(max_steps):
            self._fill_current_step(job)
            if self._is_final_step():
                break
            if not self._click_next():
                break

    def _fill_current_step(self, job) -> None:
        """Fill all visible form fields in the current modal step."""
        self._fill_text_inputs()
        self._fill_dropdowns()
        self._fill_radio_buttons()
        self._fill_checkboxes()
        self._handle_file_upload(job)

    def _fill_text_inputs(self) -> None:
        """Fill text inputs and textareas using aria-label for field identification."""
        try:
            inputs = self.driver.find_elements(
                By.XPATH,
                "//input[@type='text' or @type='number'] | //textarea"
            )
            for inp in inputs:
                aria_label = inp.get_attribute("aria-label") or ""
                if not inp.get_attribute("value"):
                    answer = self._resolve_field_answer(aria_label)
                    if answer is not None:
                        inp.clear()
                        inp.send_keys(answer)
        except Exception as exc:
            logger.debug(f"Text input fill error: {exc}")

    def _resolve_field_answer(self, field_label: str) -> Optional[str]:
        """Determine the answer for a labelled field."""
        label_lower = field_label.strip().lower()
        if "salary" in label_lower or "compensation" in label_lower:
            return self.get_salary_answer(listed_range=None)
        if label_lower:
            return self.answer_question(field_label)
        return None

    def _fill_dropdowns(self) -> None:
        """Fill select elements by matching aria-label."""
        try:
            selects = self.driver.find_elements(By.TAG_NAME, "select")
            for sel in selects:
                aria_label = sel.get_attribute("aria-label") or ""
                answer = self.answer_question(aria_label) if aria_label else None
                if answer:
                    try:
                        Select(sel).select_by_visible_text(answer)
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug(f"Dropdown fill error: {exc}")

    def _fill_radio_buttons(self) -> None:
        """Select radio buttons based on question context."""
        try:
            fieldsets = self.driver.find_elements(By.TAG_NAME, "fieldset")
            for fs in fieldsets:
                legend_text = ""
                try:
                    legend_text = fs.find_element(By.TAG_NAME, "legend").text
                except NoSuchElementException:
                    pass
                if not legend_text:
                    continue
                answer = self.answer_question(legend_text)
                radios = fs.find_elements(By.XPATH, ".//input[@type='radio']")
                for radio in radios:
                    label = radio.get_attribute("aria-label") or ""
                    if answer.lower() in label.lower():
                        try:
                            radio.click()
                        except ElementNotInteractableException:
                            pass
                        break
        except Exception as exc:
            logger.debug(f"Radio fill error: {exc}")

    def _fill_checkboxes(self) -> None:
        """Check required checkboxes (e.g. agreement/consent)."""
        try:
            checkboxes = self.driver.find_elements(
                By.XPATH, "//input[@type='checkbox']"
            )
            for cb in checkboxes:
                aria_label = (cb.get_attribute("aria-label") or "").lower()
                if any(w in aria_label for w in ["agree", "consent", "terms", "privacy"]):
                    if not cb.is_selected():
                        try:
                            cb.click()
                        except ElementNotInteractableException:
                            pass
        except Exception as exc:
            logger.debug(f"Checkbox fill error: {exc}")

    def _handle_file_upload(self, job) -> None:
        """Attach resume/cover letter when file upload fields are present."""
        try:
            resume_path = getattr(job, "resume_path", None)
            cover_letter_path = getattr(job, "cover_letter_path", None)
            uploads = self.driver.find_elements(
                By.XPATH, "//input[@type='file']"
            )
            for upload in uploads:
                aria = (upload.get_attribute("aria-label") or "").lower()
                if "cover" in aria and cover_letter_path:
                    upload.send_keys(str(cover_letter_path))
                elif resume_path:
                    upload.send_keys(str(resume_path))
        except Exception as exc:
            logger.debug(f"File upload error: {exc}")

    def _is_final_step(self) -> bool:
        """Return True if the Submit button is visible (last step)."""
        try:
            btns = self.driver.find_elements(
                By.XPATH,
                "//button[contains(@aria-label,'Submit application')]"
            )
            return len(btns) > 0
        except Exception:
            return False

    def _click_next(self) -> bool:
        """Click the Next/Review button. Returns False if not found."""
        try:
            btn = self.driver.find_element(
                By.XPATH,
                "//button[contains(@aria-label,'Next') or contains(@aria-label,'Review')]"
            )
            btn.click()
            return True
        except NoSuchElementException:
            return False

    def _submit_form(self) -> None:
        """Click the final Submit button."""
        try:
            btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@aria-label,'Submit application')]")
                )
            )
            btn.click()
        except TimeoutException:
            raise RuntimeError("Submit button not found")
