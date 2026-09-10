import os
from datetime import date, timedelta, datetime as dt
from uuid import uuid4
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models import Task, TaskLog, SkillCategory
from services.xp_service import award_xp
from services.deviation_service import check_deviation

bp = Blueprint("tasks", __name__, url_prefix="/tasks")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _parse_date(value, default=None):
    if not value:
        return default
    if isinstance(value, date):
        return value
    return dt.strptime(value, "%Y-%m-%d").date()


@bp.route("/")
@login_required
def dashboard():
    today = date.today()
    todays_tasks = Task.query.filter_by(
        user_id=current_user.id, scheduled_date=today, parent_id=None, active=True
    ).all()
    week_start = today - timedelta(days=today.weekday())
    week_tasks = Task.query.filter(
        Task.user_id == current_user.id, Task.scheduled_date >= week_start,
        Task.scheduled_date <= week_start + timedelta(days=6),
    ).count()
    return render_template("dashboard.html", tasks=todays_tasks, week_task_count=week_tasks, today=today)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_task():
    categories = SkillCategory.query.all()
    parents = Task.query.filter_by(user_id=current_user.id, active=True).all()
    if request.method == "POST":
        task = Task(
            user_id=current_user.id,
            parent_id=int(request.form["parent_id"]) if request.form.get("parent_id") else None,
            title=request.form["title"],
            description=request.form.get("description"),
            scheduled_date=_parse_date(request.form.get("scheduled_date")),
            difficulty=int(request.form.get("difficulty", 1)),
            xp_reward_base=int(request.form.get("xp_reward_base", 10)),
            recurrence=request.form.get("recurrence", "none"),
            skill_category_id=int(request.form["skill_category_id"]) if request.form.get("skill_category_id") else None,
        )
        db.session.add(task)
        db.session.commit()
        flash("Task created.", "success")
        return redirect(url_for("tasks.dashboard"))
    return render_template("task_form.html", categories=categories, parents=parents)


@bp.route("/<int:task_id>/complete", methods=["POST"])
@login_required
def complete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    pct = float(request.form.get("completion_pct", 0))
    log_date = _parse_date(request.form.get("log_date"), default=date.today())

    photo_path = None
    file = request.files.get("photo")
    if file and file.filename and _allowed(file.filename):
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        fname = f"{uuid4().hex}_{secure_filename(file.filename)}"
        file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], fname))
        photo_path = fname

    deviated = check_deviation(task.id, pct)
    log = TaskLog(task_id=task.id, log_date=log_date, completion_pct=pct,
                   notes=request.form.get("notes"), photo_path=photo_path, is_deviation=deviated)
    db.session.add(log)
    log.xp_awarded = award_xp(current_user, task, pct)
    db.session.commit()

    if deviated:
        flash(f"⚠ Significant deviation detected on '{task.title}' vs its own history.", "warning")
    flash(f"Logged {pct:.0f}% · +{log.xp_awarded} XP", "success")
    return redirect(url_for("tasks.dashboard"))


@bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for("tasks.dashboard"))
