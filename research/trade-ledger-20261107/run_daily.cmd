@echo off
rem Daily review entry: run_daily.cmd YYYY-MM-DD [jiaogedan.csv] [signals.csv]
setlocal
set PKG=%~dp0
set PY=C:\work\sourcecode\tick-stock-panel\backend\.venv\Scripts\python.exe
if "%~1"=="" (
  echo Usage: run_daily.cmd YYYY-MM-DD [jiaogedan.csv] [signals.csv]
  exit /b 2
)
set DAY=%~1
set EXTRA=
if not "%~2"=="" set EXTRA=--file "%~2"
if not "%~3"=="" set EXTRA=%EXTRA% --signals "%~3"
pushd "%PKG%"
"%PY%" -m tsp_ledger.cli daily --date %DAY% %EXTRA% --out "D:\TSP\data\user_data\trade_ledger\daily"
set RC=%ERRORLEVEL%
popd
exit /b %RC%
