# Create Desktop Shortcut for FTMO Live Bot
$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "FTMO Live Bot (10k).lnk"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "C:\personal\v_17\scripts\start_ftmo_live.bat"
$Shortcut.WorkingDirectory = "C:\personal\v_17"
$Shortcut.Description = "Start FTMO $10,000 Live Trading Bot"
$Shortcut.IconLocation = "C:\Program Files\MetaTrader 5\terminal64.exe,0"
$Shortcut.Save()

Write-Host "[SUCCESS] Shortcut created on Desktop: $ShortcutPath" -ForegroundColor Green
