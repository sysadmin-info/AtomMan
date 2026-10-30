# AtomMan LCD v9: install a scheduled task for the CURRENT interactive user.
# Run from elevated Windows PowerShell under the same user account as Windows audio.
$ErrorActionPreference = 'Stop'
$TaskName = 'AtomMan LCD Python'
$Base = Split-Path -Parent $MyInvocation.MyCommand.Path

$IsElevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsElevated) { throw 'Run PowerShell as administrator (under your ordinary Windows login account).' }

foreach ($File in @('atomman_background.py', 'screen_windows.py', 'atomman_touch_volume.py', 'screen.py', 'screen_windows.local.json')) {
    if (-not (Test-Path (Join-Path $Base $File))) { throw "Missing $File in $Base" }
}

$Python = (& py -c 'import sys;print(sys.executable)' | Select-Object -Last 1).Trim()
if (-not $Python -or -not (Test-Path $Python)) { throw 'Cannot find Python. Check: py -c "import sys;print(sys.executable)"' }
$PythonW = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
if (-not (Test-Path $PythonW)) { throw "Cannot find pythonw.exe: $PythonW" }

$User = (& whoami.exe).Trim()
$Launcher = Join-Path $Base 'atomman_background.py'
$Action = New-ScheduledTaskAction -Execute $PythonW -Argument ('"{0}"' -f $Launcher) -WorkingDirectory $Base
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
# Interactive token is important: default speaker/audio endpoint belongs to this session.
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description 'AtomMan LCD v9 COM3 + CPU/NVMe temperatures + two-way Windows volume' -Force | Out-Null

Write-Host "Registered task: $TaskName"
Write-Host "User: $User; interactive, elevated; Python: $PythonW"
Write-Host "Path: $Base"
Write-Host 'The task will run at each login without a PowerShell window.'
Write-Host "Log: $(Join-Path $Base 'logs\atomman.log')"
Write-Host 'To test right now: first close any manual AtomMan/COM3 process, then run:'
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
