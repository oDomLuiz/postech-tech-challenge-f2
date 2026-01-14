@echo off
REM Script para executar scraping.py via Agendador de Tarefas do Windows

REM Navegar para o diretório do projeto
cd "c:\Users\luizp\OneDrive\Área de Trabalho\postech-tech-challenge-f2"

REM Ativar o ambiente virtual
call .venv\Scripts\activate.bat

REM Executar o script Python
python src\scraping.py

REM Desativar o ambiente virtual (opcional)
deactivate

REM Pausar para visualizar output (remova se rodar em background)
pause