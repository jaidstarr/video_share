FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p /app/storage/videos

EXPOSE 5002

CMD ["python", "app.py"]

CMD ["gunicorn", "-b", "0.0.0.0:5002", "-w", "2", "--threads", "4", "--timeout", "300", "app:app"]