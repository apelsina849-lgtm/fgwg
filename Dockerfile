FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1

WORKDIR /app
COPY referral_start_patch.py /tmp/referral_start_patch.py
COPY maintenance_patch.py /tmp/maintenance_patch.py

# Restore the last known-good bot archive from commit bbcb53f9.
COPY app.zip.b64 /tmp/app.zip.b64
RUN python - <<'PY'
from pathlib import Path
import base64
data=base64.b64decode(Path('/tmp/app.zip.b64').read_text())
print('decoded app.zip bytes',len(data),'magic',data[:4])
if data[:2] != b'PK':
    raise RuntimeError('Unexpected app.zip payload')
Path('/tmp/app.zip').write_bytes(data)
PY
RUN python -m zipfile -t /tmp/app.zip
RUN python -m zipfile -e /tmp/app.zip /app
RUN python /tmp/referral_start_patch.py
RUN python /tmp/maintenance_patch.py
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN python -m py_compile /app/bot.py
RUN rm -f /tmp/app.zip /tmp/referral_start_patch.py /tmp/maintenance_patch.py

CMD ["python", "/app/bot.py"]
