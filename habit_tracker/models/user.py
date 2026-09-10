from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    failed_login_count = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    total_xp = db.Column(db.Integer, default=0)

    tasks = db.relationship("Task", backref="owner", lazy="dynamic", cascade="all, delete-orphan")
    templates = db.relationship("Template", backref="owner", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    @property
    def level(self) -> int:
        # Simple diminishing-returns curve: level scales with sqrt(XP)
        return int((self.total_xp / 50) ** 0.5)

    def xp_for_next_level(self) -> int:
        nxt = self.level + 1
        return (nxt ** 2) * 50
