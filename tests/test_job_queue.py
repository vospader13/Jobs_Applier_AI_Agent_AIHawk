"""
tests/test_job_queue.py

TDD tests for job_queue.py — Issue #15
Validates the get_queue() public API against the morning brief integration spec.

Spec requirements:
- Returns [] when queue.json does not exist
- Filters out jobs with fit_score < 7.5
- Deduplicates against job_history by company+title
- Returns valid jobs with all required fields present
- Handles malformed entries gracefully (missing keys = skip, not crash)
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path("D:/Repos/Jobs_Applier_AI_Agent_AIHawk")))

from src.utils.job_queue import get_queue, FIT_SCORE_THRESHOLD

REQUIRED_FIELDS = {"title", "company", "url", "board", "fit_score", "resume_pdf", "date"}

VALID_JOB = {
    "title": "Senior Engineer",
    "company": "Acme Corp",
    "url": "https://linkedin.com/jobs/1",
    "board": "linkedin",
    "fit_score": 8.5,
    "salary_range": "$120k-$150k",
    "resume_pdf": "/path/to/resume.pdf",
    "cover_letter": "/path/to/cover.pdf",
    "date": "2026-03-11",
}

BORDERLINE_JOB = {
    "title": "Mid Engineer",
    "company": "Beta Inc",
    "url": "https://indeed.com/jobs/2",
    "board": "indeed",
    "fit_score": 7.5,
    "resume_pdf": "/path/to/resume.pdf",
    "date": "2026-03-11",
}

LOW_SCORE_JOB = {
    "title": "Junior Engineer",
    "company": "Gamma LLC",
    "url": "https://ziprecruiter.com/jobs/3",
    "board": "ziprecruiter",
    "fit_score": 6.0,
    "resume_pdf": "/path/to/resume.pdf",
    "date": "2026-03-11",
}

HISTORY_WITH_ACME = (
    "| Date | Company | Title | Status | Job ID |\n"
    "| --- | --- | --- | --- | --- |\n"
    "| 2026-03-01 | Acme Corp | Senior Engineer | Applied | li_001 |\n"
)


# ---------------------------------------------------------------------------
# 1. Returns [] when queue.json does not exist
# ---------------------------------------------------------------------------

def test_get_queue_returns_empty_when_file_missing(tmp_path):
    result = get_queue(
        queue_path=tmp_path / "nonexistent.json",
        history_path=tmp_path / "nonexistent.md",
    )
    assert result == []


# ---------------------------------------------------------------------------
# 2. Filters out jobs with fit_score < 7.5 (exact boundary)
# ---------------------------------------------------------------------------

def test_get_queue_filters_low_fit_score(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([LOW_SCORE_JOB]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_includes_job_at_exact_threshold(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([BORDERLINE_JOB]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert len(result) == 1
    assert result[0]["company"] == "Beta Inc"


def test_get_queue_includes_job_above_threshold(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([VALID_JOB]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert len(result) == 1
    assert result[0]["company"] == "Acme Corp"


# ---------------------------------------------------------------------------
# 3. Deduplicates against job_history by company+title
# ---------------------------------------------------------------------------

def test_get_queue_deduplicates_by_company_and_title(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([VALID_JOB]))
    h = tmp_path / "job_history.md"
    h.write_text(HISTORY_WITH_ACME)
    result = get_queue(queue_path=q, history_path=h)
    assert result == []


def test_get_queue_dedup_different_company_passes(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([BORDERLINE_JOB]))
    h = tmp_path / "job_history.md"
    h.write_text(HISTORY_WITH_ACME)
    result = get_queue(queue_path=q, history_path=h)
    assert len(result) == 1


def test_get_queue_dedup_same_company_different_title_passes(tmp_path):
    q = tmp_path / "queue.json"
    different_title_job = {**VALID_JOB, "title": "Staff Engineer"}
    q.write_text(json.dumps([different_title_job]))
    h = tmp_path / "job_history.md"
    h.write_text(HISTORY_WITH_ACME)
    result = get_queue(queue_path=q, history_path=h)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# 4. Returns valid jobs with all required fields
# ---------------------------------------------------------------------------

def test_get_queue_returned_jobs_have_required_fields(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([VALID_JOB]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert len(result) == 1
    for field in REQUIRED_FIELDS:
        assert field in result[0], f"Missing required field: {field}"


# ---------------------------------------------------------------------------
# 5. Handles malformed entries gracefully (missing keys = skip, not crash)
# ---------------------------------------------------------------------------

def test_get_queue_skips_entry_missing_title(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "title"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_skips_entry_missing_company(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "company"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_skips_entry_missing_url(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "url"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_skips_entry_missing_fit_score(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "fit_score"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_skips_entry_missing_resume_pdf(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "resume_pdf"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_skips_entry_missing_date(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "date"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_skips_entry_missing_board(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "board"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_skips_malformed_but_returns_valid_sibling(tmp_path):
    bad = {k: v for k, v in VALID_JOB.items() if k != "title"}
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([bad, BORDERLINE_JOB]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert len(result) == 1
    assert result[0]["company"] == "Beta Inc"


def test_get_queue_handles_empty_list(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([]))
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_handles_invalid_json(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text("not valid json {{{")
    result = get_queue(queue_path=q, history_path=tmp_path / "history.md")
    assert result == []


def test_get_queue_handles_missing_history_file(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([VALID_JOB]))
    result = get_queue(queue_path=q, history_path=tmp_path / "nonexistent.md")
    assert len(result) == 1


def test_get_queue_fit_score_threshold_constant():
    assert FIT_SCORE_THRESHOLD == 7.5
