from datetime import datetime
from extensions import db

DEFAULT_CATEGORIES = ["Physical", "Mental", "Financial", "Growth"]


class SkillCategory(db.Model):
    __tablename__ = "skill_categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class UserSkill(db.Model):
    """Per-user, per-category XP -> derives a status level shown on profile."""
    __tablename__ = "user_skills"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("skill_categories.id"), nullable=False)
    xp = db.Column(db.Integer, default=0)

    category = db.relationship("SkillCategory")
    __table_args__ = (db.UniqueConstraint("user_id", "category_id", name="uq_user_category"),)

    @property
    def level(self) -> int:
        return int((self.xp / 30) ** 0.5)


class Reward(db.Model):
    """A badge/reward definition unlocked by streaks or milestones."""
    __tablename__ = "rewards"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    icon = db.Column(db.String(10), default="🏆")
    xp_threshold = db.Column(db.Integer, nullable=True)
    streak_threshold = db.Column(db.Integer, nullable=True)


class UserReward(db.Model):
    __tablename__ = "user_rewards"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reward_id = db.Column(db.Integer, db.ForeignKey("rewards.id"), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

    reward = db.relationship("Reward")
