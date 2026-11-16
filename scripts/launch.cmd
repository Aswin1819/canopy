@echo off
rem Launch the review server with the first working Python 3.8+: python3, python, then py -3.
rem (python3 is often the Microsoft Store stub on Windows; the version probe skips it.)
setlocal
set "SCRIPT=%~dp0canopy.py"
set "PROBE=import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"
python3 -c "%PROBE%" >nul 2>&1
if not errorlevel 1 goto use_python3
python -c "%PROBE%" >nul 2>&1
if not errorlevel 1 goto use_python
py -3 -c "%PROBE%" >nul 2>&1
if not errorlevel 1 goto use_py
echo canopy: no Python 3.8+ found (tried python3, python, py -3). 1>&2
exit /b 2
:use_python3
python3 "%SCRIPT%" %*
exit /b %ERRORLEVEL%
:use_python
python "%SCRIPT%" %*
exit /b %ERRORLEVEL%
:use_py
py -3 "%SCRIPT%" %*
exit /b %ERRORLEVEL%
