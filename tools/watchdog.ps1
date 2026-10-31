# qq-soul 守护：NapCat 或 bot 挂掉时自动拉起。
# 用法：powershell -ExecutionPolicy Bypass -File tools\watchdog.ps1

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'watchdog.log'

function Write-Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $log -Value $line -Encoding UTF8
    Write-Host $line
}

# 单实例：已在运行就直接退出，避免开机自启时重复拉起
$pidFile = Join-Path $logDir 'watchdog.pid'
if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Log "已有 watchdog 在运行 (pid=$oldPid)，本次退出"
        exit 0
    }
}
Set-Content -Path $pidFile -Value $PID -Encoding ASCII

function Get-Procs($name, $pattern) {
    @(Get-CimInstance Win32_Process -Filter "Name='$name'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like $pattern })
}

Write-Log "watchdog started (root=$root)"

while ($true) {
    try {
        # NapCat
        $nap = Get-Procs 'node.exe' '*napcat*'
        if ($nap.Count -eq 0) {
            Write-Log "NapCat 不在运行，拉起中"
            Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
                -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$root\tools\start_napcat.ps1" `
                -WindowStyle Hidden
        }

        # bot
        $bot = Get-Procs 'python.exe' '*main.py*'
        if ($bot.Count -eq 0) {
            Write-Log "bot 不在运行，拉起中"
            $env:PYTHONUTF8 = '1'
            $env:PYTHONIOENCODING = 'utf-8'
            Start-Process -FilePath "$root\.runtime\python\python.exe" -ArgumentList 'main.py' `
                -WorkingDirectory $root -WindowStyle Hidden `
                -RedirectStandardOutput "$logDir\bot.out.log" `
                -RedirectStandardError "$logDir\bot.err.log"
        }

        # 扫码页（掉线后要扫码时用）
        $qr = Get-Procs 'python.exe' '*qr_server.py*'
        if ($qr.Count -eq 0) {
            Write-Log "扫码页不在运行，拉起中"
            Start-Process -FilePath "$root\.runtime\python\python.exe" `
                -ArgumentList "`"$root\tools\qr_server.py`" 8790" `
                -WorkingDirectory $root -WindowStyle Hidden
        }
    } catch {
        Write-Log "watchdog 异常: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 60
}
