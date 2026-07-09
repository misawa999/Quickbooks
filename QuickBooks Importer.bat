@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  QuickBooks Journal Importer - GUI launcher
REM
REM  This is the one to give to non-technical office staff: double-
REM  click it, browse for a JSON batch file, review the report, click
REM  Import. No typing required. A console window stays open alongside
REM  the GUI on purpose -- if something ever fails to start, the error
REM  prints here instead of vanishing silently.
REM
REM  Portable like run_import.bat: runs relative to its own folder and
REM  auto-detects whichever 32-bit Python is installed (QuickBooks
REM  Desktop's SDK requires 32-bit specifically, but not any particular
REM  version).
REM ============================================================
cd /d "%~dp0"

set PYTHON_TAG=
set RAWTAG=
for /f "tokens=1" %%A in ('py -0 2^>nul ^| findstr /i "(32-bit)"') do set "RAWTAG=%%A"
if defined RAWTAG set "PYTHON_TAG=-!RAWTAG:-V:=!"

if not defined PYTHON_TAG (
    echo Could not find a 32-bit Python install on this computer.
    echo QuickBooks Desktop's SDK requires 32-bit Python specifically --
    echo install one from python.org, choosing the "Windows installer
    echo 32-bit" download, then double-click this file again. See README.md.
    pause
    exit /b 1
)

echo Starting QuickBooks Importer, Python tag %PYTHON_TAG% ...
echo.
py %PYTHON_TAG% gui.py
set GUI_EXIT=%errorlevel%

if not "%GUI_EXIT%"=="0" (
    echo.
    echo The program closed unexpectedly, exit code %GUI_EXIT% -- see any
    echo error message above. Common cause: the packages this tool needs
    echo aren't installed for this Python. Try running:
    echo   py %PYTHON_TAG% -m pip install -r requirements.txt
    echo and then double-click this file again.
    pause
)
