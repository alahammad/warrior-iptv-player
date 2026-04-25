@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=%~dp0pyi-venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo Creating build virtualenv at "%VENV_DIR%"...
  py -3.12 -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo.
    echo Failed to create virtualenv. Ensure Python 3.12 is installed and the 'py' launcher is on PATH.
    exit /b 1
  )
)

echo Using Python:
"%VENV_PY%" -c "import sys; print(' ', sys.executable); print(' ', sys.version)"
echo.

echo Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo Failed to upgrade pip.
  exit /b 1
)

echo.
echo Installing build dependencies...
"%VENV_PY%" -m pip install PyInstaller -r "..\requirements.txt"
if errorlevel 1 (
  echo.
  echo Failed to install build dependencies.
  exit /b 1
)

echo.
echo Removing old build artifacts...
if exist "pyi-build" rmdir /s /q "pyi-build"
if exist "..\dist" rmdir /s /q "..\dist"

echo.
echo Building executable with PyInstaller...
"%VENV_PY%" -m PyInstaller --noconfirm --workpath "pyi-build" --distpath "..\dist" "WarriorIPTV.spec"
if errorlevel 1 (
  echo.
  echo Build failed.
  exit /b 1
)

echo.
echo Build complete:
echo   dist\WarriorIPTV.exe

if exist "..\dist\WarriorIPTV.exe" (
  for %%I in ("..\dist\WarriorIPTV.exe") do (
    echo   Path: %%~fI
    echo   Size: %%~zI bytes
    echo   Date: %%~tI
  )
)

exit /b 0
