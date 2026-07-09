@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  QuickBooks Journal Importer - double-click launcher
REM
REM  If this fails saying Python can't be found, open a terminal
REM  and run "py -0" to see your installed versions, then change
REM  PYTHON_TAG below to match your 32-bit one (must end in -32 -
REM  QuickBooks Desktop's SDK requires 32-bit Python).
REM ============================================================
set PYTHON_TAG=-3.13-32

py %PYTHON_TAG% -c "1" >nul 2>&1
if errorlevel 1 (
    echo Could not find 32-bit Python using "py %PYTHON_TAG%".
    echo Run "py -0" in a terminal to see what's installed, then edit
    echo PYTHON_TAG at the top of this file to match.
    pause
    exit /b 1
)

echo.
echo Make sure QuickBooks Desktop is open with your company file loaded.
echo.

if "%~1"=="" (
    set /p BATCHFILE="Drag your batch JSON file onto this window, or type its path, then press Enter: "
) else (
    set BATCHFILE=%~1
)

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
