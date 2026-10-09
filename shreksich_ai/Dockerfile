FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libstdc++6 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "faster-whisper==1.2.1" "transformers==4.46.3" "pillow>=10,<12" "torch==2.5.1"
COPY community_bot.py .
CMD ["python", "community_bot.py"]
