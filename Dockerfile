FROM python:3.10-slim

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# System packages + Chrome dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ python3-dev build-essential \
    libmariadb-dev default-mysql-client \
    libpq-dev libffi-dev libssl-dev \
    libxml2-dev libxslt1-dev zlib1g-dev \
    libjpeg-dev libfreetype6-dev liblcms2-dev libopenjp2-7 libtiff-dev \
    tesseract-ocr poppler-utils \
    libnss3 libatk-bridge2.0-0 libxss1 libasound2 libgbm-dev libxshmfence1 \
    libxcomposite1 libxrandr2 libgtk-3-0 \
    curl git pkg-config wget gnupg ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome (latest stable version)
RUN mkdir -p /usr/share/man/man1 && \
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Set Chrome binary path
ENV CHROME_BIN=/usr/bin/google-chrome

# Install ChromeDriver (using direct download from known working version)
# You can update this version number from https://chromedriver.chromium.org/downloads
RUN CHROMEDRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE) && \
    echo "Installing ChromeDriver version: $CHROMEDRIVER_VERSION" && \
    wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/chromedriver && \
    rm /tmp/chromedriver.zip

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python packages
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && playwright install --with-deps  # Remove if not using Playwright

# Expose Daphne port
EXPOSE 8000

# Default command
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "energy_transition.asgi:application"]