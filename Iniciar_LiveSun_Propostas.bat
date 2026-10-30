@echo off
setlocal
title LiveSun - Propostas
cd /d "%~dp0"
if errorlevel 1 goto erro_pasta

echo ======================================================
echo              LiveSun - Propostas
echo ======================================================
echo.

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" goto erro_python
if not exist "%~dp0.env" goto erro_env
if not exist "%~dp0run.py" goto erro_programa

echo Verificando a aplicacao e a conexao com o banco...
"%PYTHON%" -c "from src.app import create_app; from src.extensions import db; from sqlalchemy import text; app = create_app(); ctx = app.app_context(); ctx.push(); db.session.execute(text('SELECT 1')); host = app.config['SERVER_HOST']; host = '127.0.0.1' if host in ('0.0.0.0', '::') else host; print('\nAcesse no navegador: http://' + host + ':' + str(app.config['SERVER_PORT'])); db.session.remove(); ctx.pop()"
if errorlevel 1 goto erro_banco

if /I "%~1"=="/verificar" (
    echo.
    echo Verificacao concluida com sucesso.
    exit /b 0
)

echo.
echo Mantenha esta janela aberta enquanto utilizar o sistema.
echo Para encerrar o servidor, pressione Ctrl+C nesta janela.
echo.
"%PYTHON%" "%~dp0run.py"
if errorlevel 1 goto erro_execucao
exit /b 0

:erro_pasta
echo ERRO: Nao foi possivel acessar a pasta do programa.
goto falha

:erro_python
echo ERRO: Ambiente virtual nao encontrado em:
echo "%PYTHON%"
echo Consulte a instalacao no README.md do projeto.
goto falha

:erro_env
echo ERRO: Arquivo .env nao encontrado na pasta do projeto.
echo Configure o arquivo a partir de .env.example.
goto falha

:erro_programa
echo ERRO: Arquivo run.py nao encontrado na pasta do projeto.
goto falha

:erro_banco
echo.
echo ERRO: Falha ao verificar a aplicacao ou conectar ao banco.
echo Confira se o MySQL esta iniciado e se o .env esta correto.
echo Os detalhes do erro estao exibidos acima.
goto falha

:erro_execucao
echo.
echo ERRO: O servidor foi encerrado com erro.
echo Confira os detalhes acima e se a porta ja esta em uso.
goto falha

:falha
echo.
if /I not "%~1"=="/verificar" pause
exit /b 1