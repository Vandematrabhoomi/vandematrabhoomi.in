@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Removing Vande Matrabhoomi auto-update tasks...
schtasks /delete /tn "VM_Morning"   /f >nul 2>&1
schtasks /delete /tn "VM_Afternoon" /f >nul 2>&1
schtasks /delete /tn "VM_Evening"   /f >nul 2>&1
schtasks /delete /tn "VM_Night"     /f >nul 2>&1
echo Done. Auto-updates have been removed.
pause
