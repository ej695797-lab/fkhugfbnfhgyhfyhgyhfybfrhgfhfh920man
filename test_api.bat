@echo off
REM ---------------------------------------------------------------
REM Yeeps API test console - run from cmd, no external tools needed.
REM Usage:  test_api.bat          (uses 127.0.0.1)
REM         test_api.bat 192.168.1.230
REM ---------------------------------------------------------------
set BASE=http://127.0.0.1:8000
if not "%~1"=="" set BASE=http://%~1:8000

echo.
echo ==============================================================
echo  Yeeps API test console   %BASE%
echo ==============================================================
echo.

REM --- 1. Photon auth (GET, works in a browser too) ---
echo [1] Photon auth
curl -s "%BASE%/?UserId=o_123&UserName=Tester"
echo.
echo.

REM --- 2. Lambda: log into an account ---
echo [2] Lambda - questLogIntoAccount
curl -s -X POST "%BASE%/2015-03-31/functions/g2_questLogIntoAccount/invocations" ^
 -H "Content-Type: application/json" ^
 -d "{\"accountID\":\"o_123\",\"oculusID\":\"Tester\",\"propertiesToGet\":[\"roleKeys\",\"currency\",\"eyeColor\",\"skinColor\"]}"
echo.
echo.

REM --- 3. Lambda: room data ---
echo [3] Lambda - fetchRoomData (official_11 / 920Man)
curl -s -X POST "%BASE%/2015-03-31/functions/g2_fetchRoomData/invocations" ^
 -H "Content-Type: application/json" ^
 -d "{\"roomKey\":\"official_11\",\"propertiesToGet\":[\"roomName\",\"themeKey\",\"dimensions\"]}"
echo.
echo.

REM --- 4. DynamoDB: GetItem ---
echo [4] DynamoDB - GetItem G2_Globals/activeBundleKey
curl -s -X POST "%BASE%/" ^
 -H "Content-Type: application/json" ^
 -H "X-Amz-Target: DynamoDB_20120810.GetItem" ^
 -d "{\"TableName\":\"G2_Globals\",\"Key\":{\"key\":{\"S\":\"activeBundleKey\"}}}"
echo.
echo.

REM --- 5. DynamoDB: BatchGetItem ---
echo [5] DynamoDB - BatchGetItem G2_Rooms
curl -s -X POST "%BASE%/" ^
 -H "Content-Type: application/json" ^
 -H "X-Amz-Target: DynamoDB_20120810.BatchGetItem" ^
 -d "{\"RequestItems\":{\"G2_Rooms\":{\"Keys\":[{\"roomKey\":{\"S\":\"tutorial\"}},{\"roomKey\":{\"S\":\"official_1\"}}],\"AttributesToGet\":[\"roomName\",\"isOfficial\"]}}}"
echo.
echo.

REM --- 6. Direct API route ---
echo [6] Direct API - /questLogIntoAccount
curl -s -X POST "%BASE%/questLogIntoAccount" ^
 -H "Content-Type: application/json" ^
 -d "{\"accountID\":\"o_123\",\"oculusID\":\"Tester\",\"propertiesToGet\":[\"currency\"]}"
echo.
echo.

echo ==============================================================
echo  Done. See logs\http_traffic.log for full request/response.
echo ==============================================================
echo.
pause