@echo off
setlocal
cd /d "%~dp0labskill-catalog"
if errorlevel 1 (
  echo LabSkill cannot find its labskill-catalog folder.
  pause
  exit /b 1
)
set "PATH=%USERPROFILE%\AppData\Roaming\npm;%USERPROFILE%\.local\bin;%PATH%"
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
  py -3 -B -m desktop
  goto done
)
python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
  python -B -m desktop
  goto done
)
echo LabSkill requires Python 3.10 or newer. Install Python and run this file again.
pause
exit /b 1
:done
set "LABSKILL_EXIT=%ERRORLEVEL%"
if not "%LABSKILL_EXIT%"=="0" pause
endlocal & exit /b %LABSKILL_EXIT%
