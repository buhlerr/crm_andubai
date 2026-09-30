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

# Inicializa migrações e sobe com gunicorn (ou waitress)
CMD ["sh", "-c", "python -m flask db upgrade && python -m flask catalogo carregar 2>/dev/null || true && gunicorn -w 4 -b 0.0.0.0:8080 --timeout 300 wsgi:app"]
