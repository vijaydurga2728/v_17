@echo off
REM Right-click this file and pick "Run as administrator".
REM Pauses (disables) the RSI2 demo poll. Re-enable later with:
REM   schtasks /Change /TN "RSI2 Demo Poll" /ENABLE
schtasks /Change /TN "RSI2 Demo Poll" /DISABLE
schtasks /Query /TN "RSI2 Demo Poll"
pause
