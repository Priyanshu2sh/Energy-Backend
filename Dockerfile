FROM python:3.10-slim

# System packages
RUN apt-get update && apt-get install -y \
    gcc g++ python3-dev build-essential \
    libmariadb-dev default-mysql-client \
    libpq-dev libffi-dev libssl-dev \
    libxml2-dev libxslt1-dev zlib1g-dev \
    libjpeg-dev libfreetype6-dev liblcms2-dev libopenjp2-7 libtiff-dev \
    tesseract-ocr poppler-utils \
    libnss3 libatk-bridge2.0-0 libxss1 libasound2 libgbm-dev libxshmfence1 \
    libxcomposite1 libxrandr2 libgtk-3-0 \
    curl git pkg-config wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy files
COPY . .

# Install Python packages
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && playwright install --with-deps  # Needed if playwright is used

# Expose Daphne port
EXPOSE 8000

# Start via Daphne
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "energy_transition.asgi:application"]
