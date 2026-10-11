FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py report.py notify.py email_template.py outbox.py digest.py ./

CMD ["python", "main.py"]
