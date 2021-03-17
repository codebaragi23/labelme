@echo off
title "build mindAT for windows10"

:: batchgotadmin
:-------------------------------------
rem  --> check for permissions
>nul 2>&1 "%systemroot%\system32\cacls.exe" "%systemroot%\system32\config\system"

rem --> if error flag set, we do not have admin.
if '%errorlevel%' neq '0' (
  echo requesting administrative privileges...
  goto uacprompt
) else ( goto gotadmin )

:uacprompt
  echo set uac = createobject^("shell.application"^) > "%temp%\getadmin.vbs"
  echo uac.shellexecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"

  "%temp%\getadmin.vbs"
  exit /b

:gotadmin
  if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
  pushd "%cd%"
  cd /d "%~dp0"
:--------------------------------------  


pip install virtualenv

set invalide_venv=

if not exist venv (
echo "------------------->>create virtualenv"
  virtualenv venv
  set invalide_venv=1
)

call venv\scripts\activate
if defined invalide_venv (
  echo "------------------->>install python packages"
  pip install -r requirements_win10_1.txt
  pip install pipwin
  pipwin install -r requirements_win10_2.txt
  pip install pyinstaller
)

if exist venv (rmdir /s /q dist)
if exist venv (rmdir /s /q build)

echo "------------------->>build spec"
pyinstaller mindAT_win10.spec
call venv\scripts\deactivate
