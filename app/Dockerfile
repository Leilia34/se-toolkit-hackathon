FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir openai

COPY . .

ENV PORT=5000
EXPOSE $PORT

CMD ["sh", "-c", "python main.py"]
