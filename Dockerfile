FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1

WORKDIR /app
COPY app.zip /tmp/app.zip
RUN python -m zipfile -e /tmp/app.zip /app \
    && rm /tmp/app.zip \
    && pip install --no-cache-dir -r /app/requirements.txt

CMD ["python", "/app/bot.py"]
