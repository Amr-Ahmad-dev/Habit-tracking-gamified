@echo off
REM Convenience wrapper - app.py now bootstraps itself (packages, PostgreSQL,
REM database, schema, seed data) on every start, so this just runs it.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python app.py
    goto :eof
)

where py >nul 2>nul
if %errorlevel%==0 (
    py app.py
    goto :eof
)

echo Python 3 is required but was not found on PATH.
echo Install it from https://www.python.org/downloads/windows/ and re-run this script.
exit /b 1
