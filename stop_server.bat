@echo off
REM Stops whatever process is listening on port 8000.
set PORT=8000
set FOUND=0

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo Stopping PID %%a on port %PORT%...
    taskkill /PID %%a /F >nul 2>&1
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo Nothing is listening on port %PORT%. Nothing to do.
) else (
    echo Port %PORT% is free.
)

REM Optional: also report MongoDB state.
echo.
sc query MongoDB | findstr /C:"STATE"

echo.
pause