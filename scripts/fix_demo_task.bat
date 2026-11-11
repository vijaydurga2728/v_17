@echo off
REM Right-click this file and pick "Run as administrator".
REM Deletes the broken RSI2 Demo Poll task and creates a correct one.
REM Also converts the XML to UTF-16 LE with BOM (required by schtasks /XML).

setlocal

echo [fix] converting XML to UTF-16 LE with BOM...
powershell -NoProfile -Command ^
  "$src='C:\personal\v_17\scripts\rsi2_demo_poll_task.xml';" ^
  "$dst='C:\personal\v_17\scripts\rsi2_demo_poll_task_utf16.xml';" ^
  "$content=Get-Content -Raw -Encoding UTF8 $src;" ^
  "[System.IO.File]::WriteAllText($dst,$content,[System.Text.Encoding]::Unicode)"
if errorlevel 1 (
  echo [fix] FAILED to convert XML
  pause
  exit /b 1
)

echo [fix] deleting old task if present...
schtasks /Delete /TN "RSI2 Demo Poll" /F >nul 2>&1

echo [fix] creating new task from XML...
schtasks /Create /TN "RSI2 Demo Poll" /XML "C:\personal\v_17\scripts\rsi2_demo_poll_task_utf16.xml"
if errorlevel 1 (
  echo [fix] FAILED to create task
  pause
  exit /b 1
)

echo [fix] running the task once to smoke-test...
schtasks /Run /TN "RSI2 Demo Poll"

echo.
echo [fix] done. Check Task Scheduler GUI; task "RSI2 Demo Poll" should show Status Ready.
echo [fix] press any key to close this window.
pause >nul
endlocal
