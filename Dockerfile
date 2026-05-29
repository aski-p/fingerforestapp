FROM python:3.11-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

ENV FRUIT_AUTO_DATA_DIR=/data

CMD ["sh", "-c", "python3 web_server.py 0.0.0.0 ${PORT:-8080}"]
