# 注册 Windows 计划任务：每天 07:30 执行 python app.py push
# 用法（在 deploy 目录下，普通 PowerShell 即可，无需管理员）：
#   powershell -ExecutionPolicy Bypass -File .\install-task.ps1
# 删除任务：
#   schtasks /Delete /TN "孕期每日推送" /F

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$app = Join-Path $root "app.py"
if (-not (Test-Path $app)) { throw "找不到 app.py：$app" }

$python = $null
foreach ($candidate in @("python", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) { throw "未找到 Python，请先安装并加入 PATH" }

$taskName = "孕期每日推送"
$action = New-ScheduledTaskAction -Execute $python -Argument "`"$app`" push" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At "07:30"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "每天 07:30 推送孕期知识与饮食建议" -Force | Out-Null

Write-Host "已注册计划任务：$taskName" -ForegroundColor Green
Write-Host "  执行：$python `"$app`" push"
Write-Host "  时间：每天 07:30（电脑开机时执行，错过会补跑）"
Write-Host ""
Write-Host "立即测试一次：" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName `"$taskName`""
Write-Host "删除任务："
Write-Host "  schtasks /Delete /TN `"$taskName`" /F"
