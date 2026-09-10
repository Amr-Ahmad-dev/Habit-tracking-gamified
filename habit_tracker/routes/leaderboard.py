from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import User

bp = Blueprint("leaderboard", __name__, url_prefix="/leaderboard")


@bp.route("/")
@login_required
def board():
    ranked = User.query.order_by(User.total_xp.desc()).all()
    rank_by_id = {u.id: i + 1 for i, u in enumerate(ranked)}
    return render_template(
        "leaderboard.html",
        top10=ranked[:10],
        best=ranked[0] if ranked else None,
        worst=ranked[-1] if ranked else None,
        my_rank=rank_by_id.get(current_user.id),
        total_users=len(ranked),
    )
