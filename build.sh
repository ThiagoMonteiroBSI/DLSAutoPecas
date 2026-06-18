#!/usr/bin/env bash
# Interrompe a execução se ocorrer algum erro
set -o errexit

# 1. Instala as dependências do projeto
pip install -r requirements.txt

# 2. Reúne todos os arquivos estáticos (CSS do Admin) para o WhiteNoise
python manage.py collectstatic --no-input

# 3. Roda as migrações no banco de dados PostgreSQL do Render
python manage.py migrate