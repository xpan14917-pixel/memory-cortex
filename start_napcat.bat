@echo off
rem 旧入口保留为转发器：实际启动逻辑在 tools\start_napcat.ps1
rem （cmd 直接起 node 会让 NapCat 登录后卡住不初始化适配器）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_napcat.ps1" %*
