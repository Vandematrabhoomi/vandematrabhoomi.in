@echo off
:: Self-elevate to admin if not already
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo  Vande Matrabhoomi -- Auto-Update Setup  [Running as Administrator]
echo  =====================================================================
echo  Source: Prasar Bharati (newsonair.gov.in / Akashvani News)
echo  Schedule: 6 times daily (every 4 hours)
echo.

set BAT=%~dp0update_news.bat

:: Remove old tasks
schtasks /delete /tn "VM_Morning"   /f >nul 2>&1
schtasks /delete /tn "VM_Afternoon" /f >nul 2>&1
schtasks /delete /tn "VM_Evening"   /f >nul 2>&1
schtasks /delete /tn "VM_Night"     /f >nul 2>&1
schtasks /delete /tn "VM_News_0600" /f >nul 2>&1
schtasks /delete /tn "VM_News_1000" /f >nul 2>&1
schtasks /delete /tn "VM_News_1400" /f >nul 2>&1
schtasks /delete /tn "VM_News_1800" /f >nul 2>&1
schtasks /delete /tn "VM_News_2200" /f >nul 2>&1
schtasks /delete /tn "VM_News_0200" /f >nul 2>&1

:: Create 6 daily tasks running as SYSTEM (runs even when not logged in)
schtasks /create /tn "VM_News_0600" /tr "cmd /c \"%BAT%\"" /sc daily /st 06:00 /ru SYSTEM /f
schtasks /create /tn "VM_News_1000" /tr "cmd /c \"%BAT%\"" /sc daily /st 10:00 /ru SYSTEM /f
schtasks /create /tn "VM_News_1400" /tr "cmd /c \"%BAT%\"" /sc daily /st 14:00 /ru SYSTEM /f
schtasks /create /tn "VM_News_1800" /tr "cmd /c \"%BAT%\"" /sc daily /st 18:00 /ru SYSTEM /f
schtasks /create /tn "VM_News_2200" /tr "cmd /c \"%BAT%\"" /sc daily /st 22:00 /ru SYSTEM /f
schtasks /create /tn "VM_News_0200" /tr "cmd /c \"%BAT%\"" /sc daily /st 02:00 /ru SYSTEM /f

echo.
echo  Done! News will auto-refresh at:
echo    6:00 AM   (morning edition)
echo   10:00 AM   (mid-morning)
echo    2:00 PM   (afternoon)
echo    6:00 PM   (evening edition)
echo   10:00 PM   (night wrap-up)
echo    2:00 AM   (early morning)
echo.
echo  Source: Prasar Bharati / Akashvani News (newsonair.gov.in)
echo  Log written to update_log.txt in this folder.
echo  To stop: run remove_auto_update.bat
echo.
pause
