from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import UserSkill, UserReward, SkillCategory

bp = Blueprint("gamification", __name__, url_prefix="/profile")


@bp.route("/")
@login_required
def profile():
    skills = {c.name: None for c in SkillCategory.query.all()}
    for s in UserSkill.query.filter_by(user_id=current_user.id):
        skills[s.category.name] = s
    rewards = UserReward.query.filter_by(user_id=current_user.id).all()
    return render_template("profile.html", skills=skills, rewards=rewards)
