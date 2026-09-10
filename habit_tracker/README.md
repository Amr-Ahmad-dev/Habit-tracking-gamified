# Habit Quest

A gamified, multi-user habit tracker built with Flask, following an MVC
layout, backed by a real SQL database (PostgreSQL or MySQL - not SQLite).

## Architecture (MVC)

```
bootstrap.py                        -> zero-setup: runs a private, self-owned
                                        PostgreSQL instance (no OS service/
                                        admin rights needed) + DB role/schema
                                        /seed provisioning and repair
config.py, extensions.py, app.py    -> app factory (calls bootstrap.py first)
models/                             -> M: SQLAlchemy models (User, Task,
                                        Template, gamification, Track)
routes/                             -> C: Flask blueprints (thin controllers)
services/                           -> business logic (XP, deviation
                                        detection, template import)
templates/, static/                 -> V: Jinja2 views + CSS/JS/music/uploads
```

Every route file stays under ~90 lines; logic that isn't pure request
handling lives in `services/`.

### Migrations

There's no Alembic/Flask-Migrate setup in this project - schema changes are
handled by `db.create_all()`, which only adds tables/columns that don't
exist yet and never touches existing ones. This is intentional for a
single-database app at this stage: it's zero-config and safe, but it means
**changing an existing column's type or renaming a column isn't handled
automatically** - only adding new tables. If the schema needs that kind of
change later, introducing Flask-Migrate is the right next step; `bootstrap.py`
was written to check for a `migrations/` directory's absence explicitly
rather than assume, so integrating Alembic later won't conflict with it.


## Setup - one command, nothing manual, no admin rights ever needed

```
python app.py
```

That's it. `app.py` runs a full bootstrap (`bootstrap.py`) before it does
anything else:

1. **Python packages** - checks each import from `requirements.txt`, installs
   whatever's missing.
2. **`.env`** - creates it if absent, or repairs a partial one (e.g. adds a
   missing `SECRET_KEY`) without ever touching an existing valid value.
3. **A private PostgreSQL instance** - this app never depends on the
   operating system's PostgreSQL service (no `systemctl`, no `brew
   services`, no Windows Service Control Manager). Instead it runs its own
   PostgreSQL server as a normal child process: its own data directory
   (`.pgdata/`, gitignored), its own port (5433 by default), started with
   whatever `initdb`/`pg_ctl` binaries are already installed anywhere on the
   machine. Since it never touches a system service, it never needs `sudo`
   or an elevated/Administrator terminal - starting your own child process
   is never a privileged operation. If no PostgreSQL binaries exist
   anywhere yet, it installs them once via the OS's own package manager
   (`apt`/`dnf`/`pacman` on Linux, `brew` on macOS, `winget` on Windows) -
   the only step that might ever need elevation, and only the very first
   time on a machine that has never had PostgreSQL at all.
4. **Database & role** - creates the `habit_user` role and `habit_tracker`
   database inside that private instance, using a superuser credential this
   script generates once (at `initdb` time) and reuses forever after - there
   is no "discover a mystery admin password" step anymore, because this app
   is the one that created that superuser account. Fixes schema/table/
   sequence privileges and writes the resulting `DATABASE_URL` into `.env`.
   Existing data is never dropped, truncated, or recreated - every check is
   "does this already work?" before "create/fix it."
5. **Schema & seed data** - `db.create_all()` (idempotent - only adds
   missing tables) plus idempotent seeding of default skill categories and
   reward badges (checks by name first, never inserts duplicates).
6. **Directories** - upload/music folders.
7. **Validation** - confirms the DB is reachable, all expected tables exist,
   seed data is present exactly once, and directories exist, before Flask
   starts serving. Fails loudly with a precise message rather than starting
   in a broken state.
8. **Port** - if 5000 is taken, picks the next free port automatically and
   prints the real URL to open.

Every step above is idempotent: running `python app.py` 1,000 times in a row
does not duplicate data, re-create existing objects, or touch anything
that's already correct. The private PostgreSQL instance is started once and
then just reused on every subsequent run - if it's already running, nothing
is restarted.

`install.sh` / `install.bat` are just convenience wrappers that call
`python app.py` (or `python3`, whichever exists on PATH).

### Pointing this app at a real/external PostgreSQL server instead

If you'd rather this app talk to a PostgreSQL server you manage yourself
(e.g. in production), just put a working `DATABASE_URL` in `.env` pointing
at it. The bootstrap always checks "does the configured `DATABASE_URL`
already work?" first - if it points anywhere other than `localhost`/
`127.0.0.1` and isn't reachable/fully functional, it stops with a clear
message rather than silently replacing your external server with a private
local one.

### The one genuinely unavoidable manual step

If PostgreSQL has never been installed on this machine at all, acquiring it
for the first time goes through the OS package manager (`apt`/`winget`/
`brew`), and that one-time install might prompt for elevation depending on
your system's policy - that's outside this script's control. After that one
install (which most machines won't even need, since PostgreSQL is commonly
already present), no further privilege is ever required again: this app's
private instance is entirely self-owned from that point on.

### Manual setup (if you'd rather not use the bootstrap)

1. Have a PostgreSQL or MySQL server running locally (or reachable).
2. `python -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` and fill in `DATABASE_URL` + `SECRET_KEY`.
5. `python app.py`


On the **first run only**, the app detects that no tables exist yet, creates
the full schema, seeds the four skill categories (Physical / Mental /
Financial / Growth) and the reward badges, and creates the upload/music
folders. Every later run leaves your data untouched.

## Feature map

- **Auth**: Flask-Login sessions, werkzeug password hashing, CSRF on every
  form (Flask-WTF), lockout after 5 failed attempts for 15 minutes,
  http-only/same-site cookies.
- **Recursive tasks**: `Task.parent_id` is self-referential - a block can
  contain blocks, which contain the leaf tasks you actually log. Same
  pattern for `Template`.
- **Templates + one-prompt import**: build recursive templates by hand, or
  paste one JSON blob (schema in `schema_prompt_format.md`) generated by any
  AI, then "instantiate" a template into real dated tasks.
- **Quantitative logging**: every completion is a 0-100% value, optional
  photo proof, optional notes.
- **Deviation alerts**: `services/deviation_service.py` compares a new entry
  against *that specific task's own* rolling history (z-score), never a
  cross-task average.
- **Stats**: seaborn/matplotlib weekly trend, monthly bars, and a per-task
  x weekday compliance heatmap (schedule/calendar-style grid), rendered
  server-side to base64 PNGs.
- **Gamification**: XP = difficulty x base reward x completion%, per-category
  skill levels (Physical/Mental/Financial/Growth), badge rewards, character
  sheet profile page.
- **Leaderboard**: ranks all users by XP, shows top 10, best/worst, and your
  own rank - fully multi-user, concurrent-safe (stateless requests + DB).
- **Focus music**: focus/gym/sleep categorized players with indefinite loop
  and per-user upload.

## Notes on scope

This is a complete, runnable application, deliberately kept concise per your
"intermediate, no junk code" instruction rather than padded to a line count.
Extend `models/`, add a blueprint, or add a service function following the
existing patterns to grow it further.
