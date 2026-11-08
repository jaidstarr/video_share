FROM python:3.11-slim AS builder 
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

COPY --from=builder /root/.local /usr/local  
COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 5002
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5002", "--workers", "4"]