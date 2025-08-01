"""Constants for the Ollama integration."""

DOMAIN = "ollama"

DEFAULT_NAME = "Ollama"

CONF_MODEL = "model"
CONF_PROMPT = "prompt"
CONF_THINK = "think"

CONF_KEEP_ALIVE = "keep_alive"
DEFAULT_KEEP_ALIVE = -1  # seconds. -1 = indefinite, 0 = never

KEEP_ALIVE_FOREVER = -1
DEFAULT_TIMEOUT = 5.0  # seconds

CONF_NUM_CTX = "num_ctx"
DEFAULT_NUM_CTX = 8192
MIN_NUM_CTX = 2048
MAX_NUM_CTX = 131072
DEFAULT_THINK = False

CONF_MAX_HISTORY = "max_history"
DEFAULT_MAX_HISTORY = 20

MAX_HISTORY_SECONDS = 60 * 60  # 1 hour

MODEL_NAMES = [  # https://ollama.com/library
    "alfred",
    "all-minilm",
    "aya-expanse",
    "aya",
    "bakllava",
    "bespoke-minicheck",
    "bge-large",
    "bge-m3",
    "codebooga",
    "codegeex4",
    "codegemma",
    "codellama",
    "codeqwen",
    "codestral",
    "codeup",
    "command-r-plus",
    "command-r",
    "dbrx",
    "deepseek-coder-v2",
    "deepseek-coder",
    "deepseek-llm",
    "deepseek-v2.5",
    "deepseek-v2",
    "dolphin-llama3",
    "dolphin-mistral",
    "dolphin-mixtral",
    "dolphin-phi",
    "dolphincoder",
    "duckdb-nsql",
    "everythinglm",
    "falcon",
    "falcon2",
    "firefunction-v2",
    "gemma",
    "gemma2",
    "glm4",
    "goliath",
    "granite-code",
    "granite3-dense",
    "granite3-guardian",
    "granite3-moe",
    "hermes3",
    "internlm2",
    "llama-guard3",
    "llama-pro",
    "llama2-chinese",
    "llama2-uncensored",
    "llama2",
    "llama3-chatqa",
    "llama3-gradient",
    "llama3-groq-tool-use",
    "llama3.1",
    "llama3.2",
    "llama3",
    "llava-llama3",
    "llava-phi3",
    "llava",
    "magicoder",
    "mathstral",
    "meditron",
    "medllama2",
    "megadolphin",
    "minicpm-v",
    "mistral-large",
    "mistral-nemo",
    "mistral-openorca",
    "mistral-small",
    "mistral",
    "mistrallite",
    "mixtral",
    "moondream",
    "mxbai-embed-large",
    "nemotron-mini",
    "nemotron",
    "neural-chat",
    "nexusraven",
    "nomic-embed-text",
    "notus",
    "notux",
    "nous-hermes",
    "nous-hermes2-mixtral",
    "nous-hermes2",
    "nuextract",
    "open-orca-platypus2",
    "openchat",
    "openhermes",
    "orca-mini",
    "orca2",
    "paraphrase-multilingual",
    "phi",
    "phi3.5",
    "phi3",
    "phind-codellama",
    "qwen",
    "qwen2-math",
    "qwen2.5-coder",
    "qwen2.5",
    "qwen2",
    "reader-lm",
    "reflection",
    "samantha-mistral",
    "shieldgemma",
    "smollm",
    "smollm2",
    "snowflake-arctic-embed",
    "solar-pro",
    "solar",
    "sqlcoder",
    "stable-beluga",
    "stable-code",
    "stablelm-zephyr",
    "stablelm2",
    "starcoder",
    "starcoder2",
    "starling-lm",
    "tinydolphin",
    "tinyllama",
    "vicuna",
    "wizard-math",
    "wizard-vicuna-uncensored",
    "wizard-vicuna",
    "wizardcoder",
    "wizardlm-uncensored",
    "wizardlm",
    "wizardlm2",
    "xwinlm",
    "yarn-llama2",
    "yarn-mistral",
    "yi-coder",
    "yi",
    "zephyr",
]
DEFAULT_MODEL = "qwen3:4b"

DEFAULT_CONVERSATION_NAME = "Ollama Conversation"
DEFAULT_AI_TASK_NAME = "Ollama AI Task"

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_MAX_HISTORY: DEFAULT_MAX_HISTORY,
}
