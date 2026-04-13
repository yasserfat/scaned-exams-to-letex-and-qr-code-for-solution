@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  Scanned Exams to LaTeX - Windows Setup
echo ============================================
echo.

:: Check for winget
winget --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: winget is not available on this machine.
    echo.
    echo winget ships with Windows 10 21H2+ and all Windows 11 installs.
    echo If it is missing, open the Microsoft Store and install
    echo "App Installer" from Microsoft, then re-run this script.
    echo.
    pause
    exit /b 1
)

:: Check for admin rights
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click setup_windows.bat and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo [1/4] Installing Python 3.11...
winget install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo       Python may already be installed - continuing.
)

:: Refresh PATH so python is available in this session
for /f "tokens=*" %%i in ('where python 2^>nul') do set PYTHON_EXE=%%i
if "%PYTHON_EXE%"=="" (
    :: Common MiKTeX default location
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe
)

echo.
echo [2/4] Installing MiKTeX (XeLaTeX + Arabic fonts)...
winget install --id MiKTeX.MiKTeX --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo       MiKTeX may already be installed - continuing.
)

echo.
echo [3/4] Installing Amiri font via MiKTeX package manager...
:: mpm is MiKTeX's CLI package manager
mpm --install=amiri >nul 2>&1
if errorlevel 1 (
    echo       Could not install Amiri via mpm - it will auto-install on first compile.
)

echo.
echo [4/4] Installing Python packages...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Check the output above for details.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Create a .env file with your ANTHROPIC_API_KEY
echo      (see README.md for all environment variables)
echo   2. Place oauth_client.json in this folder
echo      (see README.md for Google Drive OAuth setup)
echo   3. Start the server:
echo      python -m uvicorn main:app --reload
echo   4. Open http://localhost:8000
echo.
pause
