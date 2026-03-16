FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi[standard] uvicorn[standard] sqlalchemy alembic google-genai pydantic-settings python-multipart aiofiles

# Copy app source and alembic config
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY seed_mock.py .

EXPOSE 8000

# DB file is stored in /data volume
ENV DATABASE_URL=sqlite:////data/ledger.db

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
