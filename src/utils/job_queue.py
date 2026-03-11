import json
import os
from pathlib import Path
from datetime import date
from src.logging import logger

QUEUE_PATH = Path(os.environ.get(
    "AUTOAPPLY_QUEUE_PATH",
    "C:/Users/juste/Documents/ElliotBrain/Operations/job_applications/queue.json"
))
HISTORY_PATH = Path(os.environ.get(
    "AUTOAPPLY_HISTORY_PATH",
    "C:/Users/juste/Documents/ElliotBrain/Operations/job_applications/job_history.md"
))
FIT_SCORE_AUTO_APPLY = 8.0
FIT_SCORE_REVIEW_FLOOR = 7.0


def load_queue(queue_path: Path = QUEUE_PATH) -> list[dict]:
    """Load and parse queue.json. Returns [] if file missing or empty."""
    if not queue_path.exists():
        logger.warning(f"Queue file not found: {queue_path}")
        return []
    try:
        with open(queue_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to load queue: {e}")
        return []


def load_applied_ids(history_path: Path = HISTORY_PATH) -> set[str]:
    """Parse job_history.md markdown table rows and return set of job_ids (last column)."""
    applied = set()
    if not history_path.exists():
        return applied
    try:
        text = history_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("|") and line.endswith("|"):
                cols = [c.strip() for c in line.strip("|").split("|")]
                if len(cols) >= 5 and cols[0] not in ("Date", "---", ""):
                    job_id = cols[4].strip()
                    if job_id and job_id != "---":
                        applied.add(job_id)
    except Exception as e:
        logger.error(f"Failed to parse history: {e}")
    return applied


def filter_queue(
    queue: list[dict],
    applied_ids: set[str],
) -> tuple[list[dict], list[dict]]:
    """
    Filters queue into (auto_apply, review_queue).
    auto_apply: fit_score >= 8.0 and not already applied
    review_queue: 7.0 <= fit_score < 8.0 and not already applied
    Skips: already applied or fit_score < 7.0
    """
    auto_apply = []
    review_queue = []
    for job in queue:
        job_id = job.get("job_id", "")
        score = job.get("fit_score", 0.0)
        if job_id in applied_ids:
            logger.debug(f"Skipping already-applied: {job_id}")
            continue
        if score >= FIT_SCORE_AUTO_APPLY:
            auto_apply.append(job)
        elif score >= FIT_SCORE_REVIEW_FLOOR:
            review_queue.append(job)
        else:
            logger.debug(f"Skipping low-fit job (score {score}): {job_id}")
    return auto_apply, review_queue


def mark_applied(
    history_path: Path = HISTORY_PATH,
    job: dict = None,
    status: str = "Applied",
) -> None:
    """Append a new row to job_history.md after successful submission."""
    if job is None:
        return
    today = date.today().isoformat()
    company = job.get("company", "Unknown")
    title = job.get("title", "Unknown")
    job_id = job.get("job_id", "")
    row = f"| {today} | {company} | {title} | {status} | {job_id} |\n"

    if not history_path.exists():
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            "| Date | Company | Title | Status | Job ID |\n"
            "| --- | --- | --- | --- | --- |\n",
            encoding="utf-8",
        )

    with open(history_path, "a", encoding="utf-8") as f:
        f.write(row)
    logger.info(f"Marked applied: {company} - {title} ({job_id})")
