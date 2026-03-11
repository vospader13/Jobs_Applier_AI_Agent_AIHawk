import json
import pytest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path("D:/Repos/Jobs_Applier_AI_Agent_AIHawk")))

from src.utils.job_queue import (
    load_queue, load_applied_ids, filter_queue, mark_applied,
    FIT_SCORE_AUTO_APPLY, FIT_SCORE_REVIEW_FLOOR
)

SAMPLE_JOBS = [
    {"job_id": "li_001", "title": "Sr Engineer", "company": "Acme", "url": "https://example.com/1", "fit_score": 9.0, "source": "linkedin"},
    {"job_id": "li_002", "title": "Mid Engineer", "company": "Beta", "url": "https://example.com/2", "fit_score": 7.5, "source": "linkedin"},
    {"job_id": "li_003", "title": "Jr Engineer", "company": "Gamma", "url": "https://example.com/3", "fit_score": 5.0, "source": "linkedin"},
    {"job_id": "li_004", "title": "Staff Engineer", "company": "Delta", "url": "https://example.com/4", "fit_score": 8.0, "source": "linkedin"},
]


def test_load_queue_returns_list(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps(SAMPLE_JOBS[:2]))
    result = load_queue(q)
    assert len(result) == 2
    assert result[0]["job_id"] == "li_001"


def test_load_queue_missing_file(tmp_path):
    result = load_queue(tmp_path / "nonexistent.json")
    assert result == []


def test_load_queue_invalid_json(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text("not json {{{")
    result = load_queue(q)
    assert result == []


def test_load_applied_ids_parses_table(tmp_path):
    h = tmp_path / "job_history.md"
    h.write_text(
        "| Date | Company | Title | Status | Job ID |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 2026-03-01 | Acme | Sr Engineer | Applied | li_001 |\n"
        "| 2026-03-02 | Beta | Mid Engineer | Applied | li_002 |\n"
    )
    ids = load_applied_ids(h)
    assert "li_001" in ids
    assert "li_002" in ids
    assert len(ids) == 2


def test_load_applied_ids_missing_file(tmp_path):
    ids = load_applied_ids(tmp_path / "nonexistent.md")
    assert ids == set()


def test_filter_queue_auto_apply(tmp_path):
    auto, review = filter_queue([SAMPLE_JOBS[0]], set())
    assert len(auto) == 1
    assert auto[0]["job_id"] == "li_001"
    assert len(review) == 0


def test_filter_queue_review(tmp_path):
    auto, review = filter_queue([SAMPLE_JOBS[1]], set())
    assert len(auto) == 0
    assert len(review) == 1
    assert review[0]["job_id"] == "li_002"


def test_filter_queue_dedup(tmp_path):
    applied = {"li_001", "li_002"}
    auto, review = filter_queue(SAMPLE_JOBS[:2], applied)
    assert len(auto) == 0
    assert len(review) == 0


def test_filter_queue_below_floor(tmp_path):
    auto, review = filter_queue([SAMPLE_JOBS[2]], set())
    assert len(auto) == 0
    assert len(review) == 0


def test_mark_applied_appends_row(tmp_path):
    h = tmp_path / "job_history.md"
    h.write_text(
        "| Date | Company | Title | Status | Job ID |\n"
        "| --- | --- | --- | --- | --- |\n"
    )
    mark_applied(h, SAMPLE_JOBS[0], "Applied")
    content = h.read_text()
    assert "Acme" in content
    assert "li_001" in content
    assert "Applied" in content


def test_mark_applied_creates_file(tmp_path):
    h = tmp_path / "subdir" / "job_history.md"
    mark_applied(h, SAMPLE_JOBS[0], "Applied")
    assert h.exists()
    content = h.read_text()
    assert "li_001" in content
