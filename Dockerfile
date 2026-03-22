FROM python:3.11-slim
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
RUN pip install fastapi uvicorn python-multipart
WORKDIR /app
COPY . .
EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
