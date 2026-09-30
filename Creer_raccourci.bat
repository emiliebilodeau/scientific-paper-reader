@echo off
rem Cree sur le Bureau un raccourci "Lecteur scientifique" vers Lancer.bat, avec l'icone Lecteur.ico.
cd /d "%~dp0"
if not exist "Lancer.bat" goto introuvable
if not exist "Lecteur.ico" goto introuvable
set "LS_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = $env:LS_DIR.TrimEnd('\');" ^
  "$bureau = [Environment]::GetFolderPath('Desktop');" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $bureau 'Lecteur scientifique.lnk'));" ^
  "$s.TargetPath = Join-Path $d 'Lancer.bat';" ^
  "$s.WorkingDirectory = $d;" ^
  "$s.IconLocation = (Join-Path $d 'Lecteur.ico') + ',0';" ^
  "$s.Description = 'Lecteur scientifique';" ^
  "$s.Save()"
if errorlevel 1 goto echec
echo Raccourci "Lecteur scientifique" cree sur le Bureau.
echo Si le dossier du lecteur est deplace, relancer ce fichier.
pause
exit /b 0
:introuvable
echo Lancer.bat ou Lecteur.ico introuvable. Extraire tout le ZIP avant de lancer ce fichier.
pause
exit /b 1
:echec
echo La creation du raccourci a echoue. Copier le message affiche ci-dessus.
pause
exit /b 1
