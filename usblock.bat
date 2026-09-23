@echo off
REM usblock launcher for Windows.
REM   usblock.bat                open content in the terminal
REM   usblock.bat list           show drives + serials
REM   usblock.bat protect ...    encrypt files onto a drive
REM
REM First run sets up a private Python environment automatically; re-runs are
REM instant. Double-click it, or run it from cmd / PowerShell.
setlocal
set "DIR=%~dp0"
cd /d "%DIR%"

set "PYBIN=python"
where python >nul 2>nul || set "PYBIN=py"

set "VENV_PY=%DIR%.venv\Scripts\python.exe"

set "NEED_SETUP=0"
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import cryptography, psutil" >nul 2>nul || set "NEED_SETUP=1"
) else (
    set "NEED_SETUP=1"
)

if "%NEED_SETUP%"=="1" (
    echo First-time setup: creating a private environment ^(one-off^)...
    "%PYBIN%" -m venv "%DIR%.venv"
    if exist "%VENV_PY%" (
        "%VENV_PY%" -m pip install --quiet --upgrade pip
        "%VENV_PY%" -m pip install --quiet -r "%DIR%requirements.txt"
        set "RUN_PY=%VENV_PY%"
    ) else (
        echo Could not create a venv ^(read-only drive?^). Trying system Python...
        set "RUN_PY=%PYBIN%"
    )
) else (
    set "RUN_PY=%VENV_PY%"
)

"%RUN_PY%" "%DIR%usblock_cli.py" %*
endlocal
