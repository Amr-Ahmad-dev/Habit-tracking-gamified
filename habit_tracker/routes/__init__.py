def register_blueprints(app):
    from . import auth, tasks, templates_routes, stats, leaderboard, gamification_routes, music

    app.register_blueprint(auth.bp)
    app.register_blueprint(tasks.bp)
    app.register_blueprint(templates_routes.bp)
    app.register_blueprint(stats.bp)
    app.register_blueprint(leaderboard.bp)
    app.register_blueprint(gamification_routes.bp)
    app.register_blueprint(music.bp)
