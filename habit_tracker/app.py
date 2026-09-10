import os

import bootstrap

bootstrap.run()  # packages, .env, PostgreSQL install/start, role+db provisioning - must
                  # complete before config.py reads DATABASE_URL/SECRET_KEY from the environment

from flask import Flask, redirect, url_for
from flask_login import current_user

from config import Config
from extensions import db, login_manager, csrf
from routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    register_blueprints(app)

    # Post-config bootstrap: needs real app/db objects, so it runs here
    # rather than in bootstrap.run(). Idempotent - safe on every start.
    bootstrap.ensure_schema_and_seed(app, db)
    bootstrap.ensure_directories(app)
    bootstrap.validate_environment(app, db)

    @app.route("/")
    def index():
        return redirect(url_for("tasks.dashboard") if current_user.is_authenticated else url_for("auth.login"))

    return app


app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    preferred_port = int(os.environ.get("PORT", "5000"))
    port = bootstrap.resolve_free_port(preferred_port, host)
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    display_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
    print(f"\n==> Habit Quest is ready: http://{display_host}:{port}\n")
    app.run(host=host, port=port, debug=debug)
