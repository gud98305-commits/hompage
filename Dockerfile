FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

# 시스템 패키지: Pillow JPEG/PNG 지원 + 폰트 (포토부스 텍스트 렌더링)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

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

# 포토부스 데이터 + 갤러리 레퍼런스 이미지
COPY miniproject_2/photobooth/data/       ./miniproject_2/photobooth/data/
COPY miniproject_2/photobooth/public/references/ ./miniproject_2/photobooth/public/references/

RUN mkdir -p data images

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
