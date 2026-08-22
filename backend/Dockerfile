FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY rig ./rig
COPY migrations ./migrations
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "rig.main:app", "--host", "0.0.0.0", "--port", "8000"]
