#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR=${MODEL_DIR:-/models/llama-8b}

if [ ! -d "$MODEL_DIR" ]; then
  echo "ERROR: model directory $MODEL_DIR not found."
  echo "Mount your model into the container, for example: -v /local/path/llama-8b:$MODEL_DIR"
  exit 1
fi

# If user provided a command, run it (useful for debugging).
if [ $# -gt 0 ]; then
  exec "$@"
fi

# Default: run vLLM server with 1 GPU (adjust args or set env to override)
exec vllm --model "$MODEL_DIR" --host 0.0.0.0 --port 8080 --num-gpus 1
