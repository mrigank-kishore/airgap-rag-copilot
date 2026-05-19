FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ARG TORCH_CUDA=cu121
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    git \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip

# Install PyTorch for specified CUDA (default: cu121) and vLLM + common ML deps
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/${TORCH_CUDA}
RUN pip install --no-cache-dir vllm[all] transformers accelerate safetensors sentencepiece

# Create a non-root user and prepare model directory
RUN useradd -m -s /bin/bash vllm \
 && mkdir -p /models/llama-8b \
 && chown -R vllm:vllm /models

WORKDIR /home/vllm

# Copy entrypoint (set ownership later in build)
COPY entrypoint.sh /home/vllm/entrypoint.sh
RUN chown vllm:vllm /home/vllm/entrypoint.sh && chmod +x /home/vllm/entrypoint.sh

USER vllm

# Default model directory (mount your Llama 8B model here)
ENV MODEL_DIR=/models/llama-8b

EXPOSE 8080

LABEL org.opencontainers.image.description="vLLM server image for Llama 8B"

# Entrypoint script will validate the model dir and run vLLM with sensible defaults.
ENTRYPOINT ["/home/vllm/entrypoint.sh"]
