FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITE_BYTECODE=1 \
    PYTHONUTF8=1

WORKDIR /app
COPY payload.part00 payload.part01 payload.part02 payload.part03 payload.part04 payload.part05 /tmp/payload/
COPY referral_start_patch.py /tmp/referral_start_patch.py

RUN python - <<'PY'
import base64
from pathlib import Path
parts = sorted(Path('/tmp/payload').glob('payload.part*'))
out = bytearray()
for p in parts:
    data = p.read_bytes().strip()
    chunk = base64.b64decode(data, validate=False)
    print(p.name, 'b64=', len(data), 'decoded=', len(chunk))
    out.extend(chunk)
Path('/tmp/app.zip').write_bytes(out)
print('combined decoded bytes', len(out), 'magic', bytes(out[:4]))
PY
RUN python -m zipfile -t /tmp/app.zip
RUN python -m zipfile -e /tmp/app.zip /app
RUN python /tmp/referral_start_patch.py
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN python -m py_compile /app/bot.py
RUN rm -rf /tmp/payload /tmp/app.zip /tmp/referral_start_patch.py

CMD ["python", "/app/bot.py"]
