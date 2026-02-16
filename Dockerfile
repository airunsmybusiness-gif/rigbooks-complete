FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY style.py .
COPY helpers/ helpers/
COPY execution/ execution/
COPY mileage_log_FY2024-2025.html .

RUN mkdir -p data
COPY data/ data/

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
