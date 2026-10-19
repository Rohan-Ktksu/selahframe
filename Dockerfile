FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    SELAHFRAME_ONLINE=1 SELAHFRAME_STORAGE=/var/lib/selahframe \
    PIPER_DATA_DIR=/opt/voices PIPER_MODEL=en_US-ljspeech-medium \
    OMP_NUM_THREADS=2 MAX_CONCURRENT_JOBS=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-media.txt ./
RUN pip install -r requirements-media.txt
RUN mkdir -p /opt/voices && python -m piper.download_voices --data-dir /opt/voices en_US-ljspeech-medium
RUN python -c "from urllib.request import urlretrieve; urlretrieve('https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/ljspeech/medium/MODEL_CARD', '/opt/voices/en_US-ljspeech-medium.MODEL_CARD')"
COPY app ./app
COPY scripts/serve.py ./scripts/serve.py
COPY docs/THIRD_PARTY.md LICENSE ./
RUN mkdir -p /var/lib/selahframe /app/voices && chmod -R a+rX /opt/voices /app
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
