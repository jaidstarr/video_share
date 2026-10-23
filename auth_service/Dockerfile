#pulls clean image and installs requirements.txt
FROM python:3.11 AS builder 
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


#pulls a new clean image for runtime
FROM python:3.11-slim

#makes own user so the container doesnt run as root
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

#pulls pre installed python packages from builder image
COPY --from=builder /root/.local /usr/local  
COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 5001
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5001", "--workers", "4"]