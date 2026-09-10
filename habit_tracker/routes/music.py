import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models import Track

bp = Blueprint("music", __name__, url_prefix="/music")
CATEGORIES = ["focus", "gym", "sleep"]
ALLOWED_EXT = {"mp3", "ogg", "wav", "m4a"}


@bp.route("/")
@login_required
def player():
    tracks = {c: Track.query.filter_by(category=c).all() for c in CATEGORIES}
    return render_template("music.html", tracks=tracks)


@bp.route("/upload", methods=["POST"])
@login_required
def upload():
    category = request.form.get("category")
    file = request.files.get("track")
    if category not in CATEGORIES or not file or not file.filename:
        flash("Pick a category and a file.", "danger")
        return redirect(url_for("music.player"))
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        flash("Unsupported audio format.", "danger")
        return redirect(url_for("music.player"))

    folder = os.path.join(current_app.config["MUSIC_FOLDER"], category)
    os.makedirs(folder, exist_ok=True)
    fname = secure_filename(file.filename)
    file.save(os.path.join(folder, fname))
    db.session.add(Track(title=fname.rsplit(".", 1)[0], category=category, filename=fname,
                          uploaded_by=current_user.id))
    db.session.commit()
    return redirect(url_for("music.player"))
