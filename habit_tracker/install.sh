#!/usr/bin/env bash
# Convenience wrapper - app.py now bootstraps itself (packages, PostgreSQL,
# database, schema, seed data) on every start, so this just runs it.
set -e
cd "$(dirname "$0")"
PY=python3
command -v $PY >/dev/null 2>&1 || PY=python
command -v $PY >/dev/null 2>&1 || { echo "Python 3 is required but was not found on PATH."; exit 1; }
$PY app.py
