@echo off
REM Opens an inbound rule so the Quest (or any LAN device) can reach the
REM Yeeps API on port 8000. Windows blocks inbound by default on Public
REM networks, which is what produces ERR_CONNECTION_REFUSED from the headset.
REM
REM Right-click this file and choose "Run as administrator".

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: must be run as Administrator.
    echo Right-click this file ^> Run as administrator.
    pause
    exit /b 1
)

echo Adding inbound rule for TCP 8000...
netsh advfirewall firewall delete rule name="Yeeps API 8000" >nul 2>&1
netsh advfirewall firewall add rule name="Yeeps API 8000" dir=in action=allow protocol=TCP localport=8000 profile=any

echo.
echo Verifying:
netsh advfirewall firewall show rule name="Yeeps API 8000" | findstr /i "Rule Name Enabled Direction Action LocalPort"
echo.
echo Done. Test from the headset browser:
echo    http://192.168.1.230:8000/?UserId=o_1^&UserName=Tester
echo.
pause