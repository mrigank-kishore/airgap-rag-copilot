FROM python:3.12-slim

WORKDIR /app

COPY src /app/src
COPY configs /app/configs

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "localdoc_copilot.app.main"]
