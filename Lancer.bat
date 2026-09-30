@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10 ou plus est requis. Installer depuis https://www.python.org/downloads/windows/
    echo Cocher Add python.exe to PATH puis relancer ce fichier.
    pause
    exit /b 1
  )
  set "READER_PY=python"
) else (
  set "READER_PY=py -3"
)
if not exist ".venv\Scripts\python.exe" (
  %READER_PY% -m venv .venv
  if errorlevel 1 goto failure
)
.venv\Scripts\python.exe -c "import fitz" >nul 2>nul
if errorlevel 1 (
  echo Installation de l'outil PDF...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failure
)
rem Sans fenetre noire : pythonw.exe. Pour arreter, bouton Quitter dans la page
rem (le lecteur s'arrete aussi seul quand la page est fermee depuis 10 minutes).
rem Lancer.bat console : garde la fenetre et affiche les messages d'erreur.
if /i "%~1"=="console" goto console
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0
:console
.venv\Scripts\python.exe app.py
if errorlevel 1 goto failure
exit /b 0
:failure
 echo Le lancement a echoue. Copier le message affiche ci-dessus.
 pause
 exit /b 1
