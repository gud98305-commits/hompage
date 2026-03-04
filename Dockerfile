FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Python 의존성
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY backend/     ./backend/
COPY shared/      ./shared/
COPY assets/      ./assets/
COPY data/        ./data/
COPY images/      ./images/
COPY *.html       ./
COPY *.py         ./

RUN mkdir -p data images

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
