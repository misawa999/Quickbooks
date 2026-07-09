@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  QuickBooks Journal Importer - GUI launcher
REM
REM  This is the one to give to non-technical office staff: double-
REM  click it, browse for a JSON batch file, review the report, click
REM  Import. No typing, no console window.
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
    echo install one from python.org ("Windows installer (32-bit)"), then
    echo double-click this file again. See README.md for details.
    pause
    exit /b 1
)

REM pyw suppresses the console window (GUI apps don't need one). Falls
REM back to py/python if pyw isn't found for some reason.
where pyw >nul 2>&1
if errorlevel 1 (
    py %PYTHON_TAG% gui.py
) else (
    start "" pyw %PYTHON_TAG% gui.py
)
