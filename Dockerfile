FROM python:3.12-slim

# Evita criação de arquivos .pyc e força flush imediato dos logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHECKLIST_DADOS=/dados \
    SERVIDOR_HOST=0.0.0.0 \
    SERVIDOR_PORTA=8080

WORKDIR /app

# Instala dependências do sistema necessárias para compilação eventual
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Garante pasta de dados persistente
RUN mkdir -p /dados/logs /dados/backups

EXPOSE 8080

# Atualiza o banco e sobe com gunicorn. Se a migração falhar, o container NÃO sobe (melhor parado do que
# rodando com o banco errado). Só a carga do catálogo pode falhar sem impedir a subida.
CMD ["sh", "-c", "set -e; python -m flask db upgrade; python -m flask catalogo carregar || echo 'AVISO: catalogo carregar falhou'; exec gunicorn -w 4 -b 0.0.0.0:8080 --timeout 300 wsgi:app"]
