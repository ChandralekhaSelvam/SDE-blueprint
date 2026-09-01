FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/policy ./policy
COPY mock-data /srv/mock-data

ENV RUN_MODE=demo LLM_PROVIDER=mock DATA_DIR=/srv/data MOCK_DATA_DIR=/srv/mock-data
RUN mkdir -p /srv/data

EXPOSE 8000
# Cloud Run supplies PORT; default to 8000 elsewhere.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
