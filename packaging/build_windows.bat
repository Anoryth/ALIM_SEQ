@echo off
REM Construit ALIM_SEQ.exe (PyInstaller) puis l'installateur (Inno Setup).
REM A lancer depuis la RACINE du depot, sous Windows, avec Python 3.10+.
REM Prerequis : Inno Setup installe (iscc.exe dans le PATH ou ci-dessous).

setlocal
cd /d "%~dp0.."

echo === Environnement virtuel + dependances ===
python -m venv build_env || goto :err
call build_env\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip || goto :err
python -m pip install PySide6 pyvisa pyvisa-py nidaqmx pyinstaller || goto :err

echo === PyInstaller ===
pyinstaller --noconfirm --clean packaging\ALIM_SEQ.spec || goto :err

echo === Inno Setup ===
set ISCC=iscc
where %ISCC% >nul 2>nul || set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
"%ISCC%" packaging\ALIM_SEQ.iss || goto :err

echo.
echo OK : dist\ALIM_SEQ.exe (portable) et packaging\Output\ALIM_SEQ-Setup.exe (installateur)
goto :eof

:err
echo ECHEC de la construction.
exit /b 1
