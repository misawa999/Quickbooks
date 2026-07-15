@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  Build a standalone "QuickBooks Importer.exe" -- run this ONCE
REM  on a build/maintainer machine to produce a single .exe that
REM  coworkers can run with NO Python installed at all. Re-run
REM  whenever gui.py or any module it imports changes.
REM
REM  QuickBooks Desktop + the QuickBooks SDK still need to be
REM  installed separately on every machine that runs the resulting
REM  .exe -- that's a Windows/QuickBooks system integration step,
REM  not something Python packaging can bundle away. See README.md.
REM
REM  Must run under 32-bit Python, same as everything else here --
REM  the .exe it produces only works where a 32-bit process can run,
REM  matching QuickBooks Desktop's SDK requirement.
REM ============================================================
cd /d "%~dp0"

set PYTHON_TAG=
set RAWTAG=
for /f "tokens=1" %%A in ('py -0 2^>nul ^| findstr /i "(32-bit)"') do set "RAWTAG=%%A"
if defined RAWTAG set "PYTHON_TAG=-!RAWTAG:-V:=!"

if not defined PYTHON_TAG (
    echo Could not find a 32-bit Python install on this computer.
    echo Install one from python.org, choosing the "Windows installer
    echo 32-bit" download, then re-run this script.
    pause
    exit /b 1
)

echo Installing/updating build requirements for Python %PYTHON_TAG% ...
py %PYTHON_TAG% -m pip install --upgrade pyinstaller -r requirements.txt
if errorlevel 1 (
    echo.
    echo pip install failed -- see above.
    pause
    exit /b 1
)

echo.
echo Building "QuickBooks Importer.exe" ...
py %PYTHON_TAG% -m PyInstaller --noconfirm --onefile --windowed ^
    --name "QuickBooks Importer" ^
    --hidden-import win32timezone ^
    gui.py

if errorlevel 1 (
    echo.
    echo Build failed -- see the PyInstaller output above.
    pause
    exit /b 1
)

echo.
echo Done. The standalone app is at:
echo   dist\QuickBooks Importer.exe
echo.
echo That ONE file is everything a coworker's computer needs from this
echo repo -- copy it there directly. Their computer still needs
echo QuickBooks Desktop and the QuickBooks SDK installed separately
echo (see README.md), but NOT Python.
pause
