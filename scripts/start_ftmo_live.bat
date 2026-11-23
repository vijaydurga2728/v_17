@echo off
title FTMO $10,000 Live Trading Bot - ICMarkets MT5
color 0A

echo ===============================================================================
echo            FTMO $10,000 CHALLENGE LIVE AUTOMATED TRADING BOT
echo ===============================================================================
echo  Active Schedule: Monday - Friday, 24/5 Automated Execution
echo  London Session:   1:30 PM - 2:30 PM IST (03:00 - 04:00 NY) :: GBPUSD, EURUSD
echo  Cash Open Drive:  8:00 PM - 9:00 PM IST (09:30 - 10:30 NY) :: US30, USTEC, US500
echo  NY AM Session:    8:30 PM - 9:30 PM IST (10:00 - 11:00 NY) :: XAUUSD (Gold), EURUSD
echo  NY PM Session:   12:30 AM - 1:30 AM IST (14:00 - 15:00 NY) :: US30, USTEC, US500, EURUSD
echo  Target:          FTMO $10,000 Step 1 (+10%% / +$1,000)
echo  Risk Model:      0.50%% ($50) Fixed Risk per Trade -- Max 2 Trades/Day
echo ===============================================================================
echo.

cd /d C:\personal\v_17

:: Ensure python virtualenv exists
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtualenv not found at C:\personal\v_17\.venv\Scripts\python.exe
    pause
    exit /b 1
)

:: Ensure MT5 terminal GUI is running on the desktop
tasklist /FI "IMAGENAME eq terminal64.exe" 2>NUL | find /I /N "terminal64.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo [LAUNCHING] MetaTrader 5 is not open. Starting MetaTrader 5 on your screen...
    start "" "C:\Program Files\MetaTrader 5\terminal64.exe"
    ping 127.0.0.1 -n 6 >nul
) else (
    echo [OK] MetaTrader 5 is already running on your screen.
)

echo.
echo [LAUNCHING] Starting FTMO Live Execution Daemon in LIVE mode on MT5 Demo...
.venv\Scripts\python.exe scripts\live_ftmo_runner.py --loop --live

if errorlevel 1 (
    echo.
    echo [ERROR] Bot exited with error code %errorlevel%.
    pause
)
pause
