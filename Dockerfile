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
RUN python - <<'PY'
from pathlib import Path
import struct,zlib
b=Path('/tmp/app.zip').read_bytes(); p=0; count=0
while p+30<=len(b):
    if b[p:p+4] != b'PK\\x03\\x04': break
    sig,ver,flag,method,tm,dt,crc,cs,us,nl,xl=struct.unpack_from('<4s5H3L2H',b,p)
    name=b[p+30:p+30+nl].decode('utf-8','replace')
    start=p+30+nl+xl
    if not cs or start+cs>len(b): raise RuntimeError('Invalid local ZIP record: '+name)
    raw=b[start:start+cs]
    data=zlib.decompress(raw,-15) if method==8 else raw
    out=Path('/app')/name
    out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(data)
    p=start+cs; count+=1
print('restored local ZIP records',count)
if count < 3: raise RuntimeError('Archive restore found too few files')
PY
RUN python /tmp/referral_start_patch.py
RUN python /tmp/maintenance_patch.py
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN python -m py_compile /app/bot.py
RUN rm -f /tmp/app.zip /tmp/referral_start_patch.py /tmp/maintenance_patch.py

CMD ["python", "/app/bot.py"]
