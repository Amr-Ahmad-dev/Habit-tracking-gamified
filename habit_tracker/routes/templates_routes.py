import json
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models import Template
from services.template_import import import_payload, instantiate_template

bp = Blueprint("templates_bp", __name__, url_prefix="/templates")


@bp.route("/")
@login_required
def list_templates():
    roots = Template.query.filter_by(user_id=current_user.id, parent_id=None).all()
    return render_template("templates.html", templates=roots)


@bp.route("/import", methods=["GET", "POST"])
@login_required
def import_template():
    if request.method == "POST":
        try:
            payload = json.loads(request.form["payload"])
            root = import_payload(current_user.id, payload)
            flash(f"Imported template tree '{root.title}'.", "success")
            return redirect(url_for("templates_bp.list_templates"))
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            flash(f"Invalid template JSON: {e}", "danger")
    return render_template("template_import.html")


@bp.route("/<int:template_id>/instantiate", methods=["POST"])
@login_required
def instantiate(template_id):
    tpl = Template.query.filter_by(id=template_id, user_id=current_user.id).first_or_404()
    count = instantiate_template(tpl, weeks_ahead=int(request.form.get("weeks_ahead", 4)))
    flash(f"Created {count} scheduled task(s) from '{tpl.title}'.", "success")
    return redirect(url_for("templates_bp.list_templates"))


@bp.route("/<int:template_id>/delete", methods=["POST"])
@login_required
def delete_template(template_id):
    tpl = Template.query.filter_by(id=template_id, user_id=current_user.id).first_or_404()
    db.session.delete(tpl)
    db.session.commit()
    return redirect(url_for("templates_bp.list_templates"))
