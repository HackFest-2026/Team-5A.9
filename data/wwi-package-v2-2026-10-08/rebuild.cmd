@echo off
cd /d "%~dp0"
"runtime\python.exe" "scripts\build_local.py" --package .
if errorlevel 1 exit /b 1
"runtime\python.exe" "scripts\build_v2.py" --package .
if errorlevel 1 exit /b 1
"runtime\python.exe" "scripts\validate.py" --package .
if errorlevel 1 exit /b 1
"runtime\python.exe" "scripts\validate_contract.py" --package .
if errorlevel 1 exit /b 1
"runtime\python.exe" "scripts\validate_v2.py" --package .
if errorlevel 1 exit /b 1
"runtime\python.exe" "scripts\check_tasks_v2.py" --package .
if errorlevel 1 exit /b 1
echo Rebuild and validation passed.
