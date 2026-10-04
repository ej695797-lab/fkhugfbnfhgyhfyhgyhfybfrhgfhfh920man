@echo off
REM Starts the Yeeps API in its own console window.
REM Closing THIS window will NOT stop the server - that is the point.
cd /d "%~dp0"
start "Yeeps API Server" /min python main.py
echo Server starting in a minimized window titled "Yeeps API Server".
echo It takes ~5 seconds. Wait for "Application startup complete".
echo.
echo To run the tests, open another window and run:
echo     python smoke_test.py
echo.
echo To stop the server, run:  stop_server.bat
echo.
pause