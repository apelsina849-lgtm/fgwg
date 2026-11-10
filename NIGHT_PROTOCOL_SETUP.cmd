@echo off
setlocal EnableExtensions
title NIGHT PROTOCOL Setup - WLzar Company
color 0A
echo.
echo  ============================================================
echo                  WLzar Company
echo                  NIGHT PROTOCOL
echo                  Portable Setup 0.1.0
echo  ============================================================
echo.
echo  Installing to your Windows profile...
echo.

set "TARGET=%LOCALAPPDATA%\WLzar Company\NIGHT PROTOCOL"
set "BASE=https://raw.githubusercontent.com/apelsina849-lgtm/fgwg/night-protocol-portable/portable"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ErrorActionPreference='Stop';" ^
 "$target=$env:LOCALAPPDATA+'\WLzar Company\NIGHT PROTOCOL';" ^
 "New-Item -ItemType Directory -Force -Path ($target+'\game'),($target+'\launcher') ^| Out-Null;" ^
 "$files=@(" ^
 " @('game\index.html','%BASE%/game/index.html')," ^
 " @('game\style.css','%BASE%/game/style.css')," ^
 " @('game\app.js','%BASE%/game/app.js')," ^
 " @('launcher\launcher.ps1','%BASE%/launcher/launcher.ps1')," ^
 " @('NIGHT_PROTOCOL_Launcher.cmd','%BASE%/NIGHT_PROTOCOL_Launcher.cmd')," ^
 " @('manifest.json','%BASE%/manifest.json')," ^
 " @('version.json','%BASE%/version.json')," ^
 " @('README.txt','%BASE%/README.txt')" ^
 ");" ^
 "foreach($f in $files){$out=Join-Path $target $f[0]; Write-Host ('Downloading '+$f[0]); Invoke-WebRequest -UseBasicParsing -Uri $f[1] -OutFile $out};" ^
 "$desktop=[Environment]::GetFolderPath('Desktop');" ^
 "$ws=New-Object -ComObject WScript.Shell;" ^
 "$sc=$ws.CreateShortcut((Join-Path $desktop 'NIGHT PROTOCOL.lnk'));" ^
 "$sc.TargetPath=Join-Path $target 'NIGHT_PROTOCOL_Launcher.cmd';" ^
 "$sc.WorkingDirectory=$target;" ^
 "$sc.Description='NIGHT PROTOCOL - WLzar Company';" ^
 "$sc.Save();" ^
 "Start-Process (Join-Path $target 'NIGHT_PROTOCOL_Launcher.cmd')"

if errorlevel 1 (
 echo.
 echo  INSTALLATION FAILED.
 echo  Check your internet connection and Windows PowerShell.
 echo.
 pause
 exit /b 1
)

echo.
echo  Installation complete.
echo  A NIGHT PROTOCOL shortcut was added to your Desktop.
timeout /t 2 >nul
exit /b 0
