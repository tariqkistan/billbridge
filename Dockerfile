FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY legacy_sim ./legacy_sim
RUN pip install --no-cache-dir . && useradd --create-home app
USER app

EXPOSE 8000
# The same image runs the simulator: override the command with
#   uvicorn legacy_sim.app:app --host 0.0.0.0 --port 9000
CMD ["uvicorn", "billbridge.api:app", "--host", "0.0.0.0", "--port", "8000"]
