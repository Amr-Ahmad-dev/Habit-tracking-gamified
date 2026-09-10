import io
import base64
from datetime import date, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Task, TaskLog

bp = Blueprint("stats", __name__, url_prefix="/stats")
sns.set_theme(style="darkgrid")


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _logs_df(days: int) -> pd.DataFrame:
    since = date.today() - timedelta(days=days)
    rows = (
        TaskLog.query.join(Task)
        .filter(Task.user_id == current_user.id, TaskLog.log_date >= since)
        .with_entities(TaskLog.log_date, TaskLog.completion_pct, Task.title, TaskLog.is_deviation)
        .all()
    )
    return pd.DataFrame(rows, columns=["log_date", "completion_pct", "title", "is_deviation"])


@bp.route("/")
@login_required
def overview():
    df = _logs_df(90)
    if df.empty:
        return render_template("stats.html", has_data=False)

    df["log_date"] = pd.to_datetime(df["log_date"])

    # 1) Weekly compliance trend (line)
    weekly = df.set_index("log_date").resample("W-MON")["completion_pct"].mean()
    fig1, ax1 = plt.subplots(figsize=(7, 3.2))
    sns.lineplot(x=weekly.index, y=weekly.values, marker="o", ax=ax1, color="#6c5ce7")
    ax1.set_title("Weekly compliance (%)")
    ax1.set_ylabel("Avg completion %")
    ax1.set_xlabel("")
    weekly_chart = _fig_to_b64(fig1)

    # 2) Monthly compliance (bar)
    monthly = df.set_index("log_date").resample("ME")["completion_pct"].mean()
    fig2, ax2 = plt.subplots(figsize=(7, 3.2))
    sns.barplot(x=[d.strftime("%b %Y") for d in monthly.index], y=monthly.values, ax=ax2, color="#00b894")
    ax2.set_title("Monthly compliance (%)")
    ax2.set_ylabel("Avg completion %")
    monthly_chart = _fig_to_b64(fig2)

    # 3) Per-task compliance heatmap (calendar/schedule-like grid: tasks x day-of-week)
    df["dow"] = df["log_date"].dt.day_name()
    pivot = df.pivot_table(index="title", columns="dow", values="completion_pct", aggfunc="mean")
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex(columns=[d for d in order if d in pivot.columns])
    fig3, ax3 = plt.subplots(figsize=(7, max(2.5, 0.4 * len(pivot))))
    sns.heatmap(pivot, annot=True, fmt=".0f", cmap="RdYlGn", vmin=0, vmax=100, ax=ax3, cbar_kws={"label": "%"})
    ax3.set_title("Per-task compliance by weekday")
    ax3.set_xlabel("")
    ax3.set_ylabel("")
    heatmap_chart = _fig_to_b64(fig3)

    deviations = df[df["is_deviation"]].sort_values("log_date", ascending=False).head(20)

    return render_template(
        "stats.html", has_data=True, weekly_chart=weekly_chart, monthly_chart=monthly_chart,
        heatmap_chart=heatmap_chart, deviations=deviations.to_dict("records"),
        overall_pct=round(df["completion_pct"].mean(), 1),
    )
