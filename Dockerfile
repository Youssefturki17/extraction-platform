FROM python:3.10-slim

WORKDIR /app

# Installer les dependances systeme necessaires pour OpenCV, Paddle, PDF processing etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    tesseract-ocr \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Creer les dossiers de stockage
RUN mkdir -p uploads outputs benchmark/results

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
