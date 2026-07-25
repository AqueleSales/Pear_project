@echo off
title Pear Launcher - Compilador
echo =========================================
echo   PREPARANDO O PEAR LAUNCHER PARA .EXE
echo =========================================
echo.

echo [1/3] Verificando e instalando o PyInstaller...
pip install pyinstaller

echo.
echo [2/3] Compilando o launcher (Isso pode levar alguns minutos)...
REM Usa --noconsole para esconder aquela tela preta de terminal quando o amigo abrir
REM Usa --onefile para gerar apenas um arquivo .exe limpo
pyinstaller --noconsole --onefile --name "PearLauncher" launcher_desktop.py

echo.
echo [3/3] Limpando arquivos temporarios da compilacao...
rmdir /s /q build
del /q PearLauncher.spec

echo.
echo =========================================
echo COMPILACAO CONCLUIDA COM SUCESSO!
echo O seu arquivo PearLauncher.exe esta dentro da pasta "dist".
echo =========================================
pause