FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5003


CMD ["gunicorn", "app:app" "--build", "0.0.0.0:5003", "--workers", "4"]