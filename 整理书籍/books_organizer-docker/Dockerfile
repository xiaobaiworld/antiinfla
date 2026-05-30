FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    LC_ALL=C \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        calibre \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --from=books_organizer . ./books_organizer/

ENV BOOKS_ROOT=/books \
    BOOKS_DATA_DIR=/data \
    CALIBRE_EBOOK_META=/usr/bin/ebook-meta

EXPOSE 8765
CMD ["python", "-m", "books_organizer", "web", "--port", "8765"]
