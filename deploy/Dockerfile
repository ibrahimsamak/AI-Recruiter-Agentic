# deploy/Dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# non-root
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
# ONE worker on purpose — see app/main.py docstring (mounted Gradio needs it)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
