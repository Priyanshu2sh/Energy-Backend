#!/bin/bash

set -e  # Exit on error

# Timestamped log file
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="build_${TIMESTAMP}.log"
echo "📄 Logging build to $LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

# Load .env variables
ENV_FILE=".env"
if [[ ! -f $ENV_FILE ]]; then
  echo "❌ .env file not found!"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

# Validate required variables
REQUIRED_VARS=("IMAGE" "DOCKER_HUB_USERNAME" "DOCKER_HUB_TOKEN" "DEST_USER" "DEST_HOST" "PEM_FILE_PATH")
for VAR in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!VAR}" ]]; then
    echo "❌ $VAR not set in .env"
    exit 1
  fi
done

# Check if SSH is installed
if ! command -v ssh >/dev/null 2>&1; then
  echo "⚠️ OpenSSH client not found. Attempting to install..."

  # Try installing OpenSSH based on OS
  if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v apt >/dev/null 2>&1; then
      sudo apt update && sudo apt install -y openssh-client
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y openssh-clients
    elif command -v yum >/dev/null 2>&1; then
      sudo yum install -y openssh-clients
    else
      echo "❌ Could not detect supported package manager (apt, yum, or dnf). Install OpenSSH manually."
      exit 1
    fi
  elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    echo "❌ Running on Windows Git Bash: auto-install not supported. Please install OpenSSH manually via Windows Features or Chocolatey."
    exit 1
  else
    echo "❌ Unsupported OS for automatic OpenSSH installation."
    exit 1
  fi

  echo "✅ OpenSSH client installed successfully."
else
  echo "✅ OpenSSH client is already installed."
fi


SERVER_PORT="${SERVER_PORT:-22}"  # Default to port 22 if not specified

# Build the Docker image
echo "📦 Building Docker image: $IMAGE (with cache)"
BUILD_START=$(date +%s)
docker build --tag "$IMAGE" --cache-from "$IMAGE" .
BUILD_END=$(date +%s)
echo "✅ Build complete (⏱️ $((BUILD_END - BUILD_START)) seconds)"


# Login to Docker Hub
echo "🔐 Logging into Docker Hub..."
echo "$DOCKER_HUB_TOKEN" | docker login -u "$DOCKER_HUB_USERNAME" --password-stdin

# Push the image
echo "🚀 Pushing image to Docker Hub..."
PUSH_START=$(date +%s)
docker push "$IMAGE"
PUSH_END=$(date +%s)
echo "✅ Push complete (⏱️ $((PUSH_END - PUSH_START)) seconds)"
echo "🎉 Image $IMAGE successfully built and pushed!"

# Clean up dangling images
echo "🧹 Cleaning up dangling images..."
docker image prune -f
echo "✅ Cleanup complete."

# Connect to server via SSH and deploy
echo "🔗 Connecting to $DEST_USER@$DEST_HOST using key $PEM_FILE_PATH..."

ssh -i "$PEM_FILE_PATH" -tt -p "$SERVER_PORT" -o StrictHostKeyChecking=no "$DEST_USER@$DEST_HOST" << EOF
  cd ext_powerx || { echo "❌ Failed to change directory"; exit 1; }

  # Update the IMAGE variable in the .env file
  sed -i "s|^IMAGE=.*|IMAGE=$IMAGE|" .env

  # Confirm the update
  echo "✅ .env updated with IMAGE=$IMAGE"
  grep "^IMAGE=" .env

  chmod +x deploy.sh
  ./deploy.sh

  exit
EOF

echo "✅ Remote deployment triggered successfully! 🚀"
