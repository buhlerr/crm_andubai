#!/usr/bin/env bash
set -e

# Inicia o Checklist Pós-Venda em ambiente Linux (LXC, VM ou desktop)
PORTA="${PORTA:-8080}"
HOST="${HOST:-0.0.0.0}"
export FLASK_APP="wsgi"

echo "=== Iniciando Checklist Pós-Venda ==="

# Verifica se python3 está disponível
if ! command -v python3 &> /dev/null; then
    echo "Python 3 não foi encontrado. Instale com: apt update && apt install -y python3 python3-pip python3-venv"
    exit 1
fi

# Cria venv se não existir
if [ ! -d "venv" ]; then
    echo "Criando ambiente virtual (venv)..."
    python3 -m venv venv
fi

source venv/bin/activate

# Instala dependências
echo "Verificando dependências..."
pip install -q -r requirements.txt

# Atualiza banco de dados
echo "Executando migrações do banco..."
python3 -m flask db upgrade
python3 -m flask catalogo carregar 2>/dev/null || true

echo "Rodando diagnóstico..."
python3 -m flask diagnostico || true

echo ""
echo "==============================================================="
echo "  Checklist Pós-Venda rodando em http://${HOST}:${PORTA}"
echo "==============================================================="
echo ""

if command -v gunicorn &> /dev/null; then
    exec gunicorn -w 4 -b "${HOST}:${PORTA}" --timeout 300 wsgi:app
else
    exec python3 servidor.py
fi
