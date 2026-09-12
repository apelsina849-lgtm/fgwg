FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1

WORKDIR /app
COPY payload.part00 payload.part01 payload.part02 payload.part03 payload.part04 payload.part05 /tmp/payload/
COPY referral_start_patch.py /tmp/referral_start_patch.py
RUN cat /tmp/payload/payload.part00 /tmp/payload/payload.part01 /tmp/payload/payload.part02 /tmp/payload/payload.part03 /tmp/payload/payload.part04 /tmp/payload/payload.part05 > /tmp/payload.b64 \
    && python -c "import base64,hashlib; raw=base64.b64decode(open('/tmp/payload.b64','rb').read()); assert hashlib.sha256(raw).hexdigest()=='208b8df976f79c73d6b5cb9e09e3c86b53b63465241e966bbaa540c030eebb52'; open('/tmp/app.zip','wb').write(raw)" \
    && python -m zipfile -e /tmp/app.zip /app \
    && python /tmp/referral_start_patch.py \
    && rm -rf /tmp/payload /tmp/payload.b64 /tmp/app.zip /tmp/referral_start_patch.py \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && python -m py_compile /app/bot.py

CMD ["python", "/app/bot.py"]
