# Habit Quest — app.py (Developer README)

This document explains the `habit_tracker/app.py` entrypoint: what it does, why it was written this way, how to run it locally, and the known bugs/limitations. The app is a Flask-based, multi-user habit tracker with gamification. The project intentionally includes a robust, idempotent "bootstrap" system to make a single-command startup work on a fresh machine.

Status
------
- Written with Flask and SQLAlchemy.
- Designed to run locally (localhost) and is usable for development/testing.
- Not production-ready: several deliberate design choices and current limitations make this suitable for local use only.
- Incomplete: there are still known bugs and rough edges (described below).
- The bootstrap was added to fix a startup/config ordering problem (see "Reasoning" and "Known issues").

Quick start (local development)
-------------------------------
1. Clone the repo and change into the project directory.
2. From the `habit_tracker` directory run:
