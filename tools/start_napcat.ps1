# 启动 NapCat：直接起 node + 环境隔离 + 日志 + 快速登录
# 用法：start_napcat.ps1 [-Plain]
#   -Plain  不走快速登录，直接出二维码（会话失效时用）
param([switch]$Plain)

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$np = Join-Path $root '.runtime\napcat'
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:USERPROFILE = Join-Path $root '.runtime\qqhome'
$env:APPDATA = Join-Path $root '.runtime\qqhome\AppData\Roaming'
$env:LOCALAPPDATA = Join-Path $root '.runtime\qqhome\AppData\Local'
$env:TEMP = Join-Path $root '.runtime\tmp'
$env:TMP = $env:TEMP

$argList = "`"$(Join-Path $np 'index.js')`""
if (-not $Plain) { $argList += ' -q 123456789' }

Start-Process -FilePath (Join-Path $np 'node.exe') `
    -ArgumentList $argList `
    -WorkingDirectory $np `
    -RedirectStandardOutput (Join-Path $logDir 'napcat.out.log') `
    -RedirectStandardError (Join-Path $logDir 'napcat.err.log') `
    -WindowStyle Hidden
