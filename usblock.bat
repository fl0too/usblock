@echo off
setlocal enabledelayedexpansion
REM usblock launcher for Windows.
REM   Double-click it for a menu, or run from cmd/PowerShell:
REM     usblock.bat                open the menu / terminal viewer
REM     usblock.bat list           show drives + serials
REM     usblock.bat protect ...    encrypt files onto a drive
REM
REM First run sets up a private Python environment automatically; re-runs are
REM instant. The window is kept open on a double-click so you can read output.

REM --- did the user double-click us? (then we must PAUSE at the end) ---
set "DOUBLECLICK=0"
echo %cmdcmdline% | find /i "%~nx0" >nul 2>nul && set "DOUBLECLICK=1"

set "DIR=%~dp0"
cd /d "%DIR%"

REM --- find a working Python (prefer the 'py' launcher, then 'python') ------
set "PYBIN="
py -3 --version >nul 2>nul && set "PYBIN=py -3"
if not defined PYBIN (
    python --version >nul 2>nul && set "PYBIN=python"
)
if not defined PYBIN (
    echo.
    echo   Python 3 was not found on this PC.
    echo.
    echo   Install it from  https://www.python.org/downloads/  and be sure to
    echo   tick "Add python.exe to PATH" in the installer, then run this again.
    echo.
    goto :end
)

set "VENV_PY=%DIR%.venv\Scripts\python.exe"

REM --- ensure dependencies exist (create the venv on first run) -------------
set "NEED_SETUP=1"
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import cryptography, psutil" >nul 2>nul && set "NEED_SETUP=0"
)

set "USE_VENV=1"
if "!NEED_SETUP!"=="1" (
    echo First-time setup: creating a private environment ^(one-off^)...
    %PYBIN% -m venv "%DIR%.venv" 2>nul
    if exist "%VENV_PY%" (
        "%VENV_PY%" -m pip install --quiet --upgrade pip
        "%VENV_PY%" -m pip install --quiet -r "%DIR%requirements.txt"
        if errorlevel 1 (
            echo.
            echo   Could not install dependencies. Check your internet connection
            echo   and try again.
            goto :end
        )
    ) else (
        echo   Could not create a private environment ^(read-only drive?^).
        echo   Falling back to system Python.
        set "USE_VENV=0"
    )
)

REM --- run (quote the venv path in case the folder has spaces) --------------
if "!USE_VENV!"=="1" (
    "%VENV_PY%" "%DIR%usblock_cli.py" %*
) else (
    %PYBIN% "%DIR%usblock_cli.py" %*
)

:end
if "%DOUBLECLICK%"=="1" (
    echo.
    echo ------------------------------------------------------------
    pause
)
endlocal
