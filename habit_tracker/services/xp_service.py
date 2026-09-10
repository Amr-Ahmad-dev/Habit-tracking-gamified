from extensions import db
from models import UserSkill, Reward, UserReward


def award_xp(user, task, completion_pct: float) -> int:
    """XP scales with difficulty and how completely the task was done."""
    earned = round(task.difficulty * task.xp_reward_base * (completion_pct / 100))
    user.total_xp = (user.total_xp or 0) + earned

    if task.skill_category_id:
        skill = UserSkill.query.filter_by(user_id=user.id, category_id=task.skill_category_id).first()
        if not skill:
            skill = UserSkill(user_id=user.id, category_id=task.skill_category_id, xp=0)
            db.session.add(skill)
        skill.xp += earned

    _check_rewards(user)
    return earned


def _check_rewards(user) -> None:
    already = {ur.reward_id for ur in UserReward.query.filter_by(user_id=user.id)}
    for reward in Reward.query.filter(Reward.xp_threshold.isnot(None)):
        if reward.id not in already and user.total_xp >= reward.xp_threshold:
            db.session.add(UserReward(user_id=user.id, reward_id=reward.id))
