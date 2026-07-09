@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  QuickBooks Journal Importer - double-click launcher
REM
REM  Portable: always runs relative to this file's own folder (not
REM  wherever it happened to be launched from) and auto-detects
REM  whichever 32-bit Python is installed -- QuickBooks Desktop's SDK
REM  requires 32-bit specifically, but not any particular version, so
REM  this works unmodified on a different computer with a different
REM  Python version installed.
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
    echo 32-bit" download, then re-run this script. See README.md.
    pause
    exit /b 1
)

py %PYTHON_TAG% -c "1" >nul 2>&1
if errorlevel 1 (
    echo Detected Python tag "%PYTHON_TAG%" but could not run it.
    echo Run "py -0" in a terminal to check what's actually installed.
    pause
    exit /b 1
)

echo Using Python %PYTHON_TAG%
echo.
echo Make sure QuickBooks Desktop is open with your company file loaded.
echo.

if "%~1"=="" (
    set /p BATCHFILE="Drag your batch JSON file onto this window, or type its path, then press Enter: "
) else (
    set BATCHFILE=%~1
)

REM Strip any quotes the user typed (or that came with a dragged file) so
REM the path below is never wrapped twice -- double-quoting breaks parsing
REM of any path containing a space, e.g. "C:\New folder\...".
set BATCHFILE=!BATCHFILE:"=!

if not exist "!BATCHFILE!" (
    echo Could not find file: !BATCHFILE!
    pause
    exit /b 1
)

echo.
echo ================= DRY RUN (nothing written yet) =================
py %PYTHON_TAG% import_batch.py "!BATCHFILE!"
echo ===================================================================
echo.

set /p CONFIRM="Review the report above. Type YES to import into QuickBooks, anything else to cancel: "
if /I "!CONFIRM!"=="YES" (
    echo.
    echo ================= IMPORTING INTO QUICKBOOKS =================
    py %PYTHON_TAG% import_batch.py "!BATCHFILE!" --commit
    echo ===============================================================
) else (
    echo Cancelled - nothing was imported.
)

echo.
pause
