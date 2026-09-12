FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1

WORKDIR /app
COPY payload.part00 payload.part01 payload.part02 payload.part03 payload.part04 payload.part05 /tmp/payload/
COPY referral_start_patch.py /tmp/referral_start_patch.py

RUN cat /tmp/payload/payload.part00 /tmp/payload/payload.part01 /tmp/payload/payload.part02 /tmp/payload/payload.part03 /tmp/payload/payload.part04 /tmp/payload/payload.part05 > /tmp/payload.b64
RUN python -c "import base64; raw=base64.b64decode(open('/tmp/payload.b64','rb').read()); open('/tmp/app.zip','wb').write(raw); print('decoded bytes', len(raw))"
RUN python -m zipfile -t /tmp/app.zip
RUN python -m zipfile -e /tmp/app.zip /app
RUN python /tmp/referral_start_patch.py
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN python -m py_compile /app/bot.py
RUN rm -rf /tmp/payload /tmp/payload.b64 /tmp/app.zip /tmp/referral_start_patch.py

CMD ["python", "/app/bot.py"]
