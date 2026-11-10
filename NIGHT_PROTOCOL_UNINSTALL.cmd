@echo off
setlocal
title NIGHT PROTOCOL Uninstall
set "TARGET=%LOCALAPPDATA%\WLzar Company\NIGHT PROTOCOL"
echo This removes NIGHT PROTOCOL program files and local launcher files.
echo Browser save data may remain in Microsoft Edge profile storage.
choice /M "Remove NIGHT PROTOCOL"
if errorlevel 2 exit /b 0
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:LOCALAPPDATA+'\WLzar Company\NIGHT PROTOCOL'; if(Test-Path $p){Remove-Item -Recurse -Force $p}; $d=[IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'NIGHT PROTOCOL.lnk'); if(Test-Path $d){Remove-Item -Force $d}"
echo Removed.
pause
