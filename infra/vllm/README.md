# vLLM + Llama 8B Docker image

This folder contains a Dockerfile to build a vLLM server image configured to run a Llama 8B model.

Build (default CUDA 12.1 / cu121 wheels):

```bash
docker build -t vllm-llama8b -f infra/vllm/Dockerfile .
```

To build with a specific PyTorch CUDA wheel (build-arg `TORCH_CUDA`), e.g. `cu121` (default):

```bash
docker build --build-arg TORCH_CUDA=cu121 -t vllm-llama8b -f infra/vllm/Dockerfile .
```

Run (GPU):

```bash
docker run --gpus all -p 8080:8080 -v /local/path/llama-8b:/models/llama-8b --rm vllm-llama8b
```

Run with custom arguments (example CPU-only testing where an appropriate torch wheel is installed):

```bash
docker run -p 8080:8080 -v /local/path/llama-8b:/models/llama-8b --rm vllm-llama8b vllm --model /models/llama-8b --host 0.0.0.0 --port 8080 --num-gpus 0
```

Notes:
- Mount your Llama 8B model files into `/models/llama-8b` inside the container.
- The container will run `vllm` directly and expects the model mounted at `/models/llama-8b`.
- If you need a different CUDA/PyTorch combination, pass `TORCH_CUDA` at build time (for example `cu118`, `cu121`, or `cpu` if you have CPU wheels available).
