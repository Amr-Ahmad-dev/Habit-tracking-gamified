import statistics
from flask import current_app
from models import TaskLog


def check_deviation(task_id: int, new_pct: float) -> bool:
    """Compares a new completion entry against that SAME task's own history
    (baseline mean/std), never against a cross-task average. Returns True if
    the entry is a statistically significant negative deviation.
    """
    min_history = current_app.config["MIN_HISTORY_FOR_DEVIATION"]
    threshold = current_app.config["DEVIATION_ZSCORE_THRESHOLD"]

    history = [
        l.completion_pct for l in
        TaskLog.query.filter_by(task_id=task_id).order_by(TaskLog.log_date.desc()).limit(30)
    ]
    if len(history) < min_history:
        return False

    mean = statistics.mean(history)
    stdev = statistics.pstdev(history) or 1e-6
    z = (new_pct - mean) / stdev
    return z <= -threshold
