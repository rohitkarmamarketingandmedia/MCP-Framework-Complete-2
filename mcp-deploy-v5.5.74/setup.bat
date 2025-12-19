@echo off
REM ============================================
REM MCP Framework - Windows Setup
REM Run: setup.bat
REM ============================================

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║               MCP Framework 3.0 Setup                        ║
echo ║                    Windows Edition                           ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Check Python
echo [1/7] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo X Python not found!
    echo   Download from: https://www.python.org/downloads/
    echo   IMPORTANT: Check "Add Python to PATH" during install
    pause
    exit /b 1
)
python --version
echo √ Python found
echo.

REM Create virtual environment
echo [2/7] Setting up virtual environment...
if not exist "venv" (
    python -m venv venv
    echo √ Virtual environment created
) else (
    echo * Virtual environment already exists
)
echo.

REM Activate
call venv\Scripts\activate.bat

REM Install dependencies
echo [3/7] Installing dependencies...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo √ Dependencies installed
echo.

REM Create .env
echo [4/7] Configuring environment...
if not exist ".env" (
    copy .env.example .env >nul
    echo √ Created .env file
) else (
    echo * .env file exists
)

REM Generate secret key
python -c "import secrets; import re; key=secrets.token_hex(32); f=open('.env','r'); c=f.read(); f.close(); c=re.sub(r'SECRET_KEY=.*', f'SECRET_KEY={key}', c); f=open('.env','w'); f.write(c); f.close(); print('√ Generated SECRET_KEY')"
echo.

REM Check OpenAI key
findstr /C:"sk-your-openai-key" .env >nul 2>&1
if %errorlevel% equ 0 (
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo   OpenAI API Key Required
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo.
    echo   Get your key at: https://platform.openai.com/api-keys
    echo.
    set /p OPENAI_KEY="  Paste your OpenAI API key: "
    if not "%OPENAI_KEY%"=="" (
        python -c "import re; k='%OPENAI_KEY%'; f=open('.env','r'); c=f.read(); f.close(); c=re.sub(r'OPENAI_API_KEY=.*', f'OPENAI_API_KEY={k}', c); f=open('.env','w'); f.write(c); f.close()"
        echo √ OpenAI API key saved
    )
)
echo.

REM Create data directories
echo [5/7] Creating data directories...
if not exist "data" mkdir data
if not exist "data\users" mkdir data\users
if not exist "data\clients" mkdir data\clients
if not exist "data\content" mkdir data\content
if not exist "data\social" mkdir data\social
if not exist "data\schemas" mkdir data\schemas
if not exist "data\campaigns" mkdir data\campaigns
echo √ Data directories ready
echo.

REM Create admin user
echo [6/7] Setting up admin user...
python -c "from app.services.data_service import DataService; ds=DataService(); users=ds.get_all_users(); admins=[u for u in users if u.role.value=='admin']; print('EXISTS' if admins else 'NONE')" > admin_check.tmp
set /p ADMIN_STATUS=<admin_check.tmp
del admin_check.tmp

if "%ADMIN_STATUS%"=="NONE" (
    echo.
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo   Create Admin Account
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo.
    set /p ADMIN_EMAIL="  Admin email: "
    set /p ADMIN_NAME="  Admin name: "
    set /p ADMIN_PASS="  Admin password: "
    python -c "from app.services.data_service import DataService; from app.models.user import create_admin_user; admin=create_admin_user('%ADMIN_EMAIL%','%ADMIN_NAME%','%ADMIN_PASS%'); ds=DataService(); ds.save_user(admin); print('√ Admin user created')"
) else (
    echo * Admin user already exists
)
echo.

REM Verify
echo [7/7] Verifying installation...
python -c "from app import create_app; from app.models import User, Client; app=create_app('testing'); print('√ All systems operational')"
echo.

REM Done
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    √ SETUP COMPLETE!                         ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo   To start the server:
echo.
echo     start.bat
echo.
echo   Then open: http://localhost:5000
echo.
pause
