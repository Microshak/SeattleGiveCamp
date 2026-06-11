# Use LM Studio's bundled llama-server (Vulkan variant - more stable)
LLAMA_SERVER="$HOME/.lmstudio/extensions/backends/llama.cpp-linux-x86_64-vulkan-avx2-2.17.0/llama-server"

MODEL_PATH="$(dirname "$0")/../models/qwen3-coder-30b-a3b-instruct-q4_k_m.gguf"

if [ ! -f "$LLAMA_SERVER" ]; then
    echo "llama-server not found at $LLAMA_SERVER"
    exit 1
fi

if [ ! -f "$MODEL_PATH" ]; then
    echo "Model not found at $MODEL_PATH"
    exit 1
fi

# Native Qwen template (thinking enabled)
# Model trains on 262K ctx; 32K balances capability vs memory
"$LLAMA_SERVER" \
  -m "$MODEL_PATH" \
  -ngl 28 \
  --host 0.0.0.0 \
  --port 8080 \
  -c 16384 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --temp 0.2 \
  --top-p 0.9 \
  --no-warmup