from datetime import datetime, date
from extensions import db


class Task(db.Model):
    """A task or a container 'block' of sub-tasks (self-referential = recursive)."""
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)
    skill_category_id = db.Column(db.Integer, db.ForeignKey("skill_categories.id"), nullable=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    scheduled_date = db.Column(db.Date, nullable=True)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)

    recurrence = db.Column(db.String(20), default="none")  # none, daily, weekly, monthly, indefinite
    recurrence_days = db.Column(db.String(20), nullable=True)  # e.g. "MO,WE,FR"

    difficulty = db.Column(db.Integer, default=1)  # 1-5, scales XP reward
    xp_reward_base = db.Column(db.Integer, default=10)
    active = db.Column(db.Boolean, default=True)

    children = db.relationship(
        "Task", backref=db.backref("parent", remote_side=[id]),
        cascade="all, delete-orphan", single_parent=True,
    )
    logs = db.relationship("TaskLog", backref="task", lazy="dynamic", cascade="all, delete-orphan")

    def is_block(self) -> bool:
        return self.children.count() if hasattr(self.children, "count") else len(self.children) > 0

    def to_summary_dict(self):
        return {"id": self.id, "title": self.title, "children": [c.to_summary_dict() for c in self.children]}


class TaskLog(db.Model):
    """A single quantitative completion entry for a task on a given day."""
    __tablename__ = "task_logs"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    log_date = db.Column(db.Date, default=date.today, nullable=False)
    completion_pct = db.Column(db.Float, nullable=False)  # 0-100, quantitative level of completion
    notes = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)
    xp_awarded = db.Column(db.Integer, default=0)
    is_deviation = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("task_id", "log_date", name="uq_task_log_per_day"),)
