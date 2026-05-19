FROM vllm/vllm-openai:latest

# Optimize for Ada Lovelace (RTX 4080 compute capability 8.9)
ENV TORCH_CUDA_ARCH_LIST="8.9"
ENV VLLM_TORCH_COMPILE_LEVEL=3

# Define the optimized model
ENV MODEL_NAME="solidrust/Meta-Llama-3.1-8B-Instruct-AWQ"

EXPOSE 8000

ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]

# Hardcoded desktop-friendly constraints
CMD ["--model", "solidrust/Meta-Llama-3.1-8B-Instruct-AWQ", \
     "--quantization", "awq", \
     "--max-model-len", "8192", \
     "--gpu-memory-utilization", "0.90", \
     "--dtype", "float16"]