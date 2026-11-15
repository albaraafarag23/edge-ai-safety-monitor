FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# not root: a bug in the API can't touch the rest of the container. 1000 is the usual first user on the
# host, who owns the shared faces folder this service writes photos to.
USER 1000:1000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
