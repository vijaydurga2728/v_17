# PowerShell script to register FTMO 10k Live Trading Bot in Windows Task Scheduler
$TaskName = "FTMO_Live_Trading_Bot"
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument '/c "C:\personal\v_17\scripts\start_ftmo_live.bat"' -WorkingDirectory "C:\personal\v_17"

# Trigger 1: Daily at 10:10 AM Monday to Friday
$TriggerDaily = New-ScheduledTaskTrigger -Daily -At "10:10AM"

# Trigger 2: At user logon (when user logs in in the morning)
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 9)

# Register or update task
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($TriggerDaily, $TriggerLogon) -Settings $Settings -Description "FTMO $10,000 Live Trading Bot Auto-Launcher (10:10 AM - 7:00 PM IST)"
    Write-Host "[SUCCESS] Task '$TaskName' successfully registered in Windows Task Scheduler!" -ForegroundColor Green
    Write-Host "  Triggers:" -ForegroundColor Yellow
    Write-Host "  1. Daily at 10:10 AM IST"
    Write-Host "  2. Automatically at User Logon ($env:USERNAME)"
    Write-Host "  3. Execution limit: 9 hours (auto-stops after 7:00 PM IST)"
} catch {
    Write-Host "[ERROR] Failed to register task: $_" -ForegroundColor Red
}
