FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1

WORKDIR /app
COPY referral_start_patch.py /tmp/referral_start_patch.py

# Restore the last known-good bot archive from commit bbcb53f9.
RUN python - <<'PY'
from pathlib import Path
from urllib.request import urlopen
url = 'https://raw.githubusercontent.com/apelsina849-lgtm/fgwg/bbcb53f945f5e059c0fb1ea953449adfd6a0c1a7/app.zip'
with urlopen(url, timeout=30) as r:
    data = r.read()
print('downloaded app.zip bytes', len(data), 'magic', data[:4])
if len(data) != 15008 or data[:2] != b'PK':
    raise RuntimeError('Unexpected app.zip payload')
Path('/tmp/app.zip').write_bytes(data)
PY
RUN python -m zipfile -t /tmp/app.zip
RUN python -m zipfile -e /tmp/app.zip /app
RUN python /tmp/referral_start_patch.py
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN python -m py_compile /app/bot.py
RUN rm -f /tmp/app.zip /tmp/referral_start_patch.py

CMD ["python", "/app/bot.py"]
