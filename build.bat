@ECHO OFF
TITLE "build mindAT for windows"

:: BatchGotAdmin
:-------------------------------------
REM  --> Check for permissions
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

REM --> If error flag set, we do not have admin.
IF '%errorlevel%' NEQ '0' (
  ECHO Requesting administrative privileges...
  GOTO UACPrompt
) ELSE ( GOTO gotAdmin )

:UACPrompt
  ECHO Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
  ECHO UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"

  "%temp%\getadmin.vbs"
  EXIT /B

:gotAdmin
  IF EXIST "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
  PUSHD "%CD%"
  CD /D "%~dp0"
:--------------------------------------  


pip install virtualenv

SET invalide_venv=

IF NOT EXIST venv (
  virtualenv venv
  SET invalide_venv=1
  ECHO "------------------->>Create virtualenv"
)

CALL venv\Scripts\activate
IF defined invalide_venv (
  pip install -r requirements_windows1.txt
  pip install pipwin
  pipwin install -r requirements_windows2.txt
  pip install pyinstaller
  ECHO "------------------->>Install python packages"
)

RMDIR /s /q dist build
ECHO "------------------->>Build spec"
pyinstaller mindAT_windows.spec

CALL venv\Scripts\deactivate
