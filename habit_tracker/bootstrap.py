"""
Habit Quest - bootstrap system.

Makes `python app.py` a genuine single-command startup on a fresh machine.
It does NOT rely on the operating system's PostgreSQL service. Instead it
runs a private, self-owned PostgreSQL instance: its own data directory, its
own port, started as a normal child process using whatever `initdb`/`pg_ctl`
binaries are already installed. That process never needs `sudo` or
Administrator rights, because it never touches systemd/launchd/the Windows
Service Control Manager - it just launches `postgres` the same way any
other program launches a child process.

Design rules followed throughout this file:
  - Every step checks real state before acting (idempotent, re-run-safe).
  - Existing data is never dropped/truncated/recreated - see the specific
    comment above the one narrow, clearly-guarded exception to that rule.
  - Secrets (passwords, SECRET_KEY) are generated once and reused forever
    after (never regenerated arbitrarily), never printed or logged.
  - This module imports nothing from config/extensions/models at module
    level, so it can safely run *before* those are configured (avoids the
    circular "config reads DATABASE_URL before .env is loaded" bug).
"""
import getpass
import glob
import importlib
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")
DB_NAME = "habit_tracker"
DB_ROLE = "habit_user"

# This app's own private PostgreSQL cluster - fully separate from any
# system-wide PostgreSQL install. Only the *binaries* are shared; the data
# directory, port, and superuser credential all belong solely to this app.
PGDATA_DIR = os.path.join(ROOT, ".pgdata")
PG_SUPERUSER_CRED_FILE = os.path.join(PGDATA_DIR, ".superuser_credentials")
PG_PROVEN_WORKING_MARKER = os.path.join(PGDATA_DIR, ".proven_working")
DEFAULT_PRIVATE_PORT = 5433


# --------------------------------------------------------------- logging

def log(level, msg):
    print(f"[{level}] {msg}")


def fatal(msg):
    """A precise, actionable failure - never pretend success."""
    log("FATAL", msg)
    sys.exit(1)


# ------------------------------------------------------------- packages

# pip distribution name -> the module name actually used by `import`
_IMPORT_NAMES = {
    "Flask-Login": "flask_login", "Flask-WTF": "flask_wtf",
    "Flask-SQLAlchemy": "flask_sqlalchemy", "psycopg2-binary": "psycopg2",
    "PyMySQL": "pymysql", "email-validator": "email_validator",
    "Pillow": "PIL", "python-dotenv": "dotenv",
}


def ensure_python_packages():
    print("\n== Python packages ==")
    req_path = os.path.join(ROOT, "requirements.txt")
    missing = []
    with open(req_path) as f:
        for line in f:
            pkg = re.split(r"[=<>]", line.strip())[0].strip()
            if not pkg or pkg.startswith("#"):
                continue
            mod = _IMPORT_NAMES.get(pkg, pkg.lower().replace("-", "_"))
            try:
                importlib.import_module(mod)
            except ImportError:
                missing.append(pkg)

    if not missing:
        log("OK", "All required Python packages already installed.")
        return

    log("FIX", f"Installing missing packages: {', '.join(missing)}")
    cmd = [sys.executable, "-m", "pip", "install", "-r", req_path]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        # Modern Debian/Ubuntu marks the system Python "externally managed"
        subprocess.run(cmd + ["--break-system-packages"], check=True)
    importlib.invalidate_caches()


# ------------------------------------------------------------------ env

def _parse_env_file():
    values = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip()
    return values


def _write_env(values):
    with open(ENV_PATH, "w") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")
    log("OK", f".env written to {ENV_PATH} (secret values are never printed).")


def ensure_dotenv():
    """Creates .env if missing, or repairs a partial one - fills in only
    what's absent (SECRET_KEY, defaults) without touching existing values.
    Handles a setup that stopped halfway (resumes safely)."""
    print("\n== .env ==")
    values = _parse_env_file()
    changed = False

    if not values.get("SECRET_KEY"):
        values["SECRET_KEY"] = secrets.token_hex(32)
        changed = True
        log("FIX", "Generated a new SECRET_KEY.")
    else:
        log("OK", "Existing SECRET_KEY preserved.")

    for key, default in (("HOST", "0.0.0.0"), ("FLASK_DEBUG", "false"), ("PORT", "5000")):
        if key not in values:
            values[key] = default
            changed = True

    if changed or not os.path.exists(ENV_PATH):
        _write_env(values)

    for k, v in values.items():
        os.environ.setdefault(k, v)


def set_database_url(url):
    values = _parse_env_file()
    values["DATABASE_URL"] = url
    _write_env(values)
    os.environ["DATABASE_URL"] = url


def ensure_gitignore():
    path = os.path.join(ROOT, ".gitignore")
    required = [".env", "__pycache__/", "*.pyc", "venv/",
                "static/uploads/*", "static/music/*/*", ".pgdata/"]
    existing = open(path).read().splitlines() if os.path.exists(path) else []
    missing = [r for r in required if r not in existing]
    if missing:
        with open(path, "a") as f:
            for r in missing:
                f.write(r + "\n")


# ------------------------------------------------------------- networking

def _port_open(host="127.0.0.1", port=5432, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_free_port(start_port, host="127.0.0.1"):
    port = start_port
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                port += 1
    fatal(f"Could not find a free port starting from {start_port}.")


def resolve_free_port(preferred_port, host="0.0.0.0"):
    """Used for the Flask web server port (separate from the private
    PostgreSQL port below)."""
    bind_host = "" if host == "0.0.0.0" else host
    port = _find_free_port(preferred_port, bind_host)
    if port != preferred_port:
        log("WARN", f"Port {preferred_port} was busy - using {port} instead.")
    return port


# ------------------------------------------------------- locate binaries

def _bin_name(name):
    return name + (".exe" if platform.system() == "Windows" else "")


def _bin_path(bin_dir, name):
    return os.path.join(bin_dir, _bin_name(name))


def find_postgres_bin_dir():
    """Locates a directory containing initdb/pg_ctl/postgres, reusing
    whatever's already installed (system package, prior winget/brew/apt
    install, a version manager, etc.) rather than assuming a location.
    This is what makes the private-cluster approach work immediately for
    anyone who already has PostgreSQL installed anywhere on the machine -
    including the common case of it being installed but not on PATH.
    """
    exe = shutil.which("initdb") or shutil.which("psql")
    if exe:
        candidate = os.path.dirname(os.path.abspath(exe))
        if os.path.exists(_bin_path(candidate, "initdb")):
            return candidate

    system = platform.system()
    if system == "Windows":
        search_globs = [
            r"C:\Program Files\PostgreSQL\*\bin\initdb.exe",
            r"C:\Program Files (x86)\PostgreSQL\*\bin\initdb.exe",
        ]
    elif system == "Darwin":
        search_globs = [
            "/opt/homebrew/Cellar/postgresql*/*/bin/initdb",
            "/usr/local/Cellar/postgresql*/*/bin/initdb",
            "/opt/homebrew/opt/postgresql*/bin/initdb",
        ]
    else:
        search_globs = [
            "/usr/lib/postgresql/*/bin/initdb",
            "/usr/pgsql-*/bin/initdb",
        ]

    matches = []
    for pattern in search_globs:
        matches += glob.glob(pattern)
    if matches:
        matches.sort(reverse=True)  # prefer the newest installed version
        return os.path.dirname(matches[0])
    return None


# -------------------------------------------------- acquire binaries

def linux_pkg_manager():
    for mgr in ("apt-get", "dnf", "yum", "pacman"):
        if shutil.which(mgr):
            return mgr
    return None


def _sudo_prefix():
    if os.geteuid() == 0:
        return []
    return ["sudo"] if shutil.which("sudo") else []


def linux_install_postgres():
    mgr = linux_pkg_manager()
    if not mgr:
        return False
    sudo = _sudo_prefix()
    try:
        if mgr == "apt-get":
            subprocess.run(sudo + ["apt-get", "update"], check=False)
            subprocess.run(sudo + ["apt-get", "install", "-y", "postgresql", "postgresql-contrib"], check=True)
        elif mgr in ("dnf", "yum"):
            subprocess.run(sudo + [mgr, "install", "-y", "postgresql-server", "postgresql-contrib"], check=True)
        elif mgr == "pacman":
            subprocess.run(sudo + ["pacman", "-Sy", "--noconfirm", "postgresql"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        log("WARN", f"Automatic PostgreSQL install failed: {e}")
        return False


def mac_install_postgres():
    if not shutil.which("brew"):
        return False
    try:
        subprocess.run(["brew", "install", "postgresql@16"], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def windows_install_postgres():
    """Installs PostgreSQL via winget. This one-time install step is the
    only part of the whole bootstrap that might need elevation (winget
    itself may prompt for it) - but it only needs to happen ONCE, ever,
    on a given machine. After this, the app runs its own private instance
    and never touches Windows service control again."""
    if not shutil.which("winget"):
        return False
    log("FIX", "Installing PostgreSQL via winget (silent)...")
    cmd = ["winget", "install", "--id", "PostgreSQL.PostgreSQL.16", "-e", "--silent",
           "--accept-package-agreements", "--accept-source-agreements"]
    try:
        subprocess.run(cmd, check=True, timeout=1800)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        log("WARN", f"winget install failed: {e}")
        return False


def ensure_postgres_binaries():
    bin_dir = find_postgres_bin_dir()
    if bin_dir:
        log("OK", f"Found PostgreSQL binaries at {bin_dir}.")
        return bin_dir

    log("FIX", "No PostgreSQL binaries found anywhere on this machine - attempting install...")
    system = platform.system()
    ok = (linux_install_postgres() if system == "Linux"
          else mac_install_postgres() if system == "Darwin"
          else windows_install_postgres() if system == "Windows"
          else False)
    if ok:
        time.sleep(2)
        bin_dir = find_postgres_bin_dir()
    if not bin_dir:
        fatal(
            "PostgreSQL binaries could not be found or installed automatically.\n"
            "Install PostgreSQL manually, then re-run `python app.py`:\n"
            "  Windows: https://www.postgresql.org/download/windows/\n"
            "  macOS:   brew install postgresql@16\n"
            "  Linux:   your distro's postgresql package\n"
            "This only needs to happen once - after that, this app runs its own "
            "private PostgreSQL instance and never depends on any system service."
        )
    return bin_dir


# --------------------------------------------------- private DB cluster

def _read_private_superuser_password():
    if os.path.exists(PG_SUPERUSER_CRED_FILE):
        with open(PG_SUPERUSER_CRED_FILE) as f:
            return f.read().strip()
    return None


def _write_private_superuser_password(password):
    os.makedirs(PGDATA_DIR, exist_ok=True)
    with open(PG_SUPERUSER_CRED_FILE, "w") as f:
        f.write(password)
    try:
        os.chmod(PG_SUPERUSER_CRED_FILE, 0o600)
    except (AttributeError, NotImplementedError, OSError):
        pass  # best-effort; NTFS already restricts to the owning user by default


def _private_cluster_valid():
    return os.path.isfile(os.path.join(PGDATA_DIR, "PG_VERSION"))


def _private_cluster_running(bin_dir):
    try:
        r = subprocess.run([_bin_path(bin_dir, "pg_ctl"), "status", "-D", PGDATA_DIR],
                            capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _init_private_cluster(bin_dir):
    """Own key, generated once, reused forever after - this eliminates the
    'discover a mystery admin password' problem entirely, because this app
    is the one that created this superuser account in the first place."""
    password = secrets.token_urlsafe(20)
    pwfile = os.path.join(ROOT, f".pwtmp_{secrets.token_hex(4)}")
    with open(pwfile, "w") as f:
        f.write(password)
    try:
        log("FIX", f"Initializing a private PostgreSQL data directory at {PGDATA_DIR}...")
        r = subprocess.run(
            [_bin_path(bin_dir, "initdb"), "-D", PGDATA_DIR, "-U", "postgres",
             "--pwfile", pwfile, "--auth=scram-sha-256", "--auth-local=trust", "-E", "UTF8"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            fatal(f"initdb failed: {(r.stderr or r.stdout).strip()}")
    except subprocess.TimeoutExpired:
        fatal("initdb did not finish within 120 seconds - check antivirus/disk activity "
              f"and re-run: python app.py")
    finally:
        if os.path.exists(pwfile):
            os.remove(pwfile)
    _write_private_superuser_password(password)
    log("OK", "Private PostgreSQL data directory initialized.")


def _start_private_cluster(bin_dir, port):
    log_path = os.path.join(PGDATA_DIR, "server.log")
    pid_file = os.path.join(PGDATA_DIR, "postmaster.pid")
    # A stale lock file from an unclean shutdown makes pg_ctl refuse to
    # start even though nothing is actually running - clear it first.
    if os.path.exists(pid_file) and not _private_cluster_running(bin_dir):
        os.remove(pid_file)

    # IMPORTANT (Windows): pg_ctl start launches postgres.exe as a
    # long-running background server. On Windows that child process can
    # inherit our stdout/stderr pipe handles, so capture_output=True would
    # make Python wait forever for those pipes to close - they never will,
    # because the server is supposed to keep running. Discard the output
    # instead (postgres's own output already goes to `-l log_path`), and
    # bound the wait with a timeout as a second safety net.
    try:
        r = subprocess.run(
            [_bin_path(bin_dir, "pg_ctl"), "start", "-D", PGDATA_DIR, "-l", log_path,
             "-o", f"-p {port} -h 127.0.0.1 -c unix_socket_directories="],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        # pg_ctl itself didn't report back in time - but the server it
        # launched may well have started successfully anyway (the same
        # handle-inheritance quirk above). Check reality instead of
        # assuming failure.
        log("WARN", "pg_ctl did not report back within 30s - checking whether "
                     "the server actually started anyway...")
        return _private_cluster_running(bin_dir) or _port_open("127.0.0.1", port)


def ensure_private_postgres(port):
    """Runs a PostgreSQL instance this process fully owns. Never touches a
    system service, so it can never be blocked by the 'Access is denied'
    class of error a Windows service start requires elevation for."""
    print(f"\n== Private PostgreSQL instance (port {port}) ==")
    bin_dir = ensure_postgres_binaries()

    if not _private_cluster_valid():
        _init_private_cluster(bin_dir)
    else:
        log("OK", f"Private data directory already initialized ({PGDATA_DIR}).")

    if _private_cluster_running(bin_dir):
        log("OK", "Private PostgreSQL instance is already running.")
        return

    log("FIX", f"Starting private PostgreSQL instance on 127.0.0.1:{port}...")
    if _start_private_cluster(bin_dir, port):
        for _ in range(15):
            if _port_open("127.0.0.1", port):
                log("OK", "Private PostgreSQL instance started.")
                return
            time.sleep(1)

    proven = os.path.exists(PG_PROVEN_WORKING_MARKER)
    if proven:
        # This cluster has successfully served the app before, which means
        # it may hold real data - the safety rule against destroying data
        # applies here without exception. Diagnose, don't delete.
        log_tail = ""
        log_path = os.path.join(PGDATA_DIR, "server.log")
        if os.path.exists(log_path):
            with open(log_path) as f:
                log_tail = "".join(f.readlines()[-15:])
        fatal(
            "The private PostgreSQL instance failed to start, and it has served "
            "this app successfully before - it may hold real data, so it will "
            "NOT be touched automatically.\n"
            f"Data directory: {PGDATA_DIR}\n"
            f"Last log lines:\n{log_tail}\n"
            "Common causes: another process is already using this port, or the "
            "machine lost power during a write. Free the port or investigate the "
            "log above, then re-run: python app.py"
        )

    # Never proven to have worked yet (first run, or a previous run never
    # got this far) - safe to treat as not-yet-real and reinitialize once.
    log("WARN", "Private data directory never successfully started before - "
                "reinitializing it (nothing has been proven to depend on it yet).")
    shutil.rmtree(PGDATA_DIR, ignore_errors=True)
    _init_private_cluster(bin_dir)
    if not _start_private_cluster(bin_dir, port):
        fatal(f"Could not start a private PostgreSQL instance even after "
              f"reinitializing. Check {os.path.join(PGDATA_DIR, 'server.log')}.")
    for _ in range(15):
        if _port_open("127.0.0.1", port):
            log("OK", "Private PostgreSQL instance started after reinitialization.")
            return
        time.sleep(1)
    fatal("Private PostgreSQL instance did not become reachable after starting.")


def _mark_proven_working():
    os.makedirs(PGDATA_DIR, exist_ok=True)
    open(PG_PROVEN_WORKING_MARKER, "w").close()


# ------------------------------------------------- role / db / grants

def _try_connect(dsn):
    import psycopg2
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.close()
        return True
    except Exception:
        return False


def _app_role_fully_functional(dsn):
    """Proves real read/write rights, not just a successful login - this is
    what catches a role that authenticates but lacks table privileges."""
    import psycopg2
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.execute("CREATE TABLE IF NOT EXISTS _bootstrap_probe (id int)")
        cur.execute("DROP TABLE _bootstrap_probe")
        cur.close()
        conn.close()
        return True
    except Exception:
        return False


def _existing_role_password():
    """Reuses the password from a previous (possibly interrupted) run
    instead of generating a new one every time - keeps re-runs idempotent."""
    m = re.search(r"://[^:]+:([^@]+)@", os.environ.get("DATABASE_URL", ""))
    return m.group(1) if m else None


def _provision_role_and_db(admin_dsn, db_dsn_maintenance, port, role_password):
    """admin_dsn: connects to the 'postgres' maintenance DB as superuser.
    Creates/repairs the app role, database, and every privilege the models
    need, entirely idempotently."""
    import psycopg2
    from psycopg2 import sql

    conn = psycopg2.connect(admin_dsn)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (DB_ROLE,))
    if cur.fetchone():
        cur.execute(sql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(sql.Identifier(DB_ROLE)), (role_password,))
        log("OK", f"Role '{DB_ROLE}' already existed - password refreshed.")
    else:
        cur.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(DB_ROLE)), (role_password,))
        log("FIX", f"Created role '{DB_ROLE}'.")

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
    if cur.fetchone():
        log("OK", f"Database '{DB_NAME}' already exists - preserved as-is.")
    else:
        cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(DB_NAME), sql.Identifier(DB_ROLE)))
        log("FIX", f"Created database '{DB_NAME}'.")

    cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
        sql.Identifier(DB_NAME), sql.Identifier(DB_ROLE)))
    cur.close()
    conn.close()

    # Schema/table/sequence grants must run against a connection to DB_NAME
    # itself - covers a role that authenticates but lacks table privileges.
    conn2 = psycopg2.connect(db_dsn_maintenance)
    conn2.autocommit = True
    cur2 = conn2.cursor()
    role = sql.Identifier(DB_ROLE)
    cur2.execute(sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(role))
    cur2.execute(sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA public TO {}").format(role))
    cur2.execute(sql.SQL("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {}").format(role))
    cur2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {}").format(role))
    cur2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {}").format(role))
    cur2.close()
    conn2.close()
    log("OK", "Schema/table/sequence privileges ensured for the app role.")


def _resolve_private_pg_port():
    """Reuses the port from an existing local DATABASE_URL so re-runs stay
    on the same instance; otherwise picks a free one starting at 5433
    (deliberately not 5432, to never collide with a real system instance)."""
    url = os.environ.get("DATABASE_URL", "")
    m = re.search(r"@(?:localhost|127\.0\.0\.1):(\d+)/", url)
    if m:
        return int(m.group(1))
    return _find_free_port(DEFAULT_PRIVATE_PORT)


def ensure_app_role_and_database():
    """Idempotent end-to-end DB provisioning against this app's private
    PostgreSQL instance. Only touches what's actually broken/missing;
    never drops or recreates an existing database."""
    print("\n== Database & role ==")
    url = os.environ.get("DATABASE_URL", "")
    existing_dsn = url.replace("postgresql+psycopg2", "postgresql") if url else ""
    is_local = (not url) or re.search(r"@(localhost|127\.0\.0\.1):", url) is not None

    if existing_dsn and _app_role_fully_functional(existing_dsn):
        log("OK", "Existing DATABASE_URL already connects with full privileges - nothing to repair.")
        _mark_proven_working()
        return

    if url and not is_local:
        # DATABASE_URL points at an external server the user configured
        # themselves - never silently replace their explicit configuration
        # with a local private instance.
        fatal(
            "DATABASE_URL points at a non-local PostgreSQL server that isn't fully "
            "reachable/functional right now. Since it's an external server, this "
            "script will not silently replace it with a private local instance.\n"
            "Fix the external server/credentials, or remove DATABASE_URL from .env "
            "to let this script manage a private local instance automatically."
        )

    port = _resolve_private_pg_port()
    ensure_private_postgres(port)

    role_password = _existing_role_password() or secrets.token_urlsafe(16)
    su_password = _read_private_superuser_password()
    if not su_password:
        fatal("Private PostgreSQL instance has no recorded superuser credential - "
              "this should not happen. Delete the .pgdata directory and re-run "
              "python app.py to reinitialize from scratch.")

    admin_dsn = f"postgresql://postgres:{su_password}@127.0.0.1:{port}/postgres"
    db_dsn = f"postgresql://postgres:{su_password}@127.0.0.1:{port}/{DB_NAME}"
    _provision_role_and_db(admin_dsn, db_dsn, port, role_password)

    new_url = f"postgresql+psycopg2://{DB_ROLE}:{role_password}@127.0.0.1:{port}/{DB_NAME}"
    if not _app_role_fully_functional(new_url.replace("postgresql+psycopg2", "postgresql")):
        fatal("Provisioning ran but the application role still cannot fully connect. "
              f"Check {os.path.join(PGDATA_DIR, 'server.log')} for details.")
    set_database_url(new_url)
    _mark_proven_working()
    log("OK", "Application role/database ready.")


# --------------------------------------------------- schema, seed, dirs

def ensure_schema_and_seed(app, db):
    """Creates any SQLAlchemy tables that don't exist yet (never drops or
    recreates existing ones) and seeds default rows without duplicating
    anything that's already there."""
    print("\n== Schema & seed data ==")

    migrations_dir = os.path.join(ROOT, "migrations")
    if os.path.isdir(migrations_dir) and os.listdir(migrations_dir):
        log("WARN", "A migrations/ directory exists - this project's schema is "
                     "expected to be managed by Alembic/Flask-Migrate, not "
                     "db.create_all(). Skipping automatic table creation; "
                     "run your migration tool (e.g. `flask db upgrade`) instead.")
    else:
        with app.app_context():
            db.create_all()  # per-table checkfirst - safe with existing data/tables
            log("OK", "SQLAlchemy schema ensured (existing tables/data untouched).")

    with app.app_context():
        _seed_idempotent()
        db.session.commit()


def _seed_idempotent():
    from extensions import db
    from models import SkillCategory, Reward
    from models.gamification import DEFAULT_CATEGORIES

    existing_cats = {c.name for c in SkillCategory.query.all()}
    added = [name for name in DEFAULT_CATEGORIES if name not in existing_cats]
    for name in added:
        db.session.add(SkillCategory(name=name))
    if added:
        log("FIX", f"Seeded {len(added)} missing skill categor{'y' if len(added) == 1 else 'ies'}.")

    reward_defs = [
        ("First Step", "Log your first task", "🌱", 1),
        ("Consistent", "Reach 500 total XP", "🔥", 500),
        ("Dedicated", "Reach 2000 total XP", "💎", 2000),
        ("Master", "Reach 5000 total XP", "👑", 5000),
    ]
    existing_rewards = {r.name for r in Reward.query.all()}
    added_r = [d for d in reward_defs if d[0] not in existing_rewards]
    for name, desc, icon, xp in added_r:
        db.session.add(Reward(name=name, description=desc, icon=icon, xp_threshold=xp))
    if added_r:
        log("FIX", f"Seeded {len(added_r)} missing reward badge(s).")

    if not added and not added_r:
        log("OK", "Seed data already present exactly once - nothing to do.")


def ensure_directories(app):
    for path in (app.config["UPLOAD_FOLDER"],
                 os.path.join(app.config["MUSIC_FOLDER"], "focus"),
                 os.path.join(app.config["MUSIC_FOLDER"], "gym"),
                 os.path.join(app.config["MUSIC_FOLDER"], "sleep")):
        os.makedirs(path, exist_ok=True)
    log("OK", "Upload/music directories ensured.")


# -------------------------------------------------------------- validate

def validate_environment(app, db):
    """Final pre-serve check. Reports exactly what's wrong (never silently
    swallowed) and exits fatally rather than starting Flask in a broken
    state - but only after every automatic repair above has run."""
    print("\n== Validation ==")
    from sqlalchemy import inspect as sa_inspect, text

    problems = []
    url = os.environ.get("DATABASE_URL", "")
    m = re.search(r"@[^:]+:(\d+)/", url)
    port = int(m.group(1)) if m else 5432
    if not _port_open("127.0.0.1", port):
        problems.append(f"PostgreSQL is not reachable on 127.0.0.1:{port}.")

    with app.app_context():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception as e:
            problems.append(f"SQLAlchemy cannot execute a query: {e}")

        inspector = sa_inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        expected_tables = set(db.metadata.tables.keys())
        missing = expected_tables - existing_tables
        if missing:
            problems.append(f"Missing tables: {', '.join(sorted(missing))}")

        try:
            from models import SkillCategory
            from models.gamification import DEFAULT_CATEGORIES
            cat_names = [c.name for c in SkillCategory.query.all()]
            if len(cat_names) != len(set(cat_names)):
                problems.append("Duplicate skill categories detected in seed data.")
            if not set(DEFAULT_CATEGORIES).issubset(set(cat_names)):
                problems.append("Default skill categories are missing.")
        except Exception as e:
            problems.append(f"Could not verify seed data: {e}")

    for path in (app.config["UPLOAD_FOLDER"], app.config["MUSIC_FOLDER"]):
        if not os.path.isdir(path):
            problems.append(f"Missing required directory: {path}")

    if problems:
        for p in problems:
            log("WARN", p)
        fatal("Environment validation failed after repair attempts - see warnings above.")

    log("OK", "Environment validated: DB reachable, schema complete, seed data present, directories ready.")


# ------------------------------------------------------------ orchestrator

def run():
    """Everything that must happen BEFORE config.py/extensions.py are
    imported: env vars have to exist first, or Config's class-body read of
    DATABASE_URL fails (the exact bug this replaces)."""
    print(f"\n=== Habit Quest bootstrap ({platform.system()}) ===")
    ensure_gitignore()
    ensure_python_packages()
    ensure_dotenv()
    ensure_app_role_and_database()
