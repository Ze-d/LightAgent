import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-5.4-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))


MAX_STEPS = int(os.getenv("MAX_STEPS", "5"))


CONTEXT_MAX_INPUT_TOKENS = int(os.getenv("CONTEXT_MAX_INPUT_TOKENS", "8000"))
CONTEXT_MEMORY_MAX_TOKENS = int(os.getenv("CONTEXT_MEMORY_MAX_TOKENS", "1200"))

CONTEXT_PIPELINE_ENABLED = os.getenv("CONTEXT_PIPELINE_ENABLED", "true").strip().lower() == "true"
CONTEXT_DEDUP_ENABLED = os.getenv("CONTEXT_DEDUP_ENABLED", "true").strip().lower() == "true"

CONTEXT_SCORE_SYSTEM_PROMPT = int(os.getenv("CONTEXT_SCORE_SYSTEM_PROMPT", "100"))
CONTEXT_SCORE_RECENT_EXCHANGE = int(os.getenv("CONTEXT_SCORE_RECENT_EXCHANGE", "90"))
CONTEXT_SCORE_RECENT_TOOL_OUTPUT = int(os.getenv("CONTEXT_SCORE_RECENT_TOOL_OUTPUT", "85"))
CONTEXT_SCORE_SUMMARY = int(os.getenv("CONTEXT_SCORE_SUMMARY", "70"))
CONTEXT_SCORE_OLDER_EXCHANGE = int(os.getenv("CONTEXT_SCORE_OLDER_EXCHANGE", "60"))
CONTEXT_SCORE_OLDER_TOOL_OUTPUT = int(os.getenv("CONTEXT_SCORE_OLDER_TOOL_OUTPUT", "50"))
CONTEXT_SCORE_TRANSIENT_MEMORY = int(os.getenv("CONTEXT_SCORE_TRANSIENT_MEMORY", "30"))

CONTEXT_RECENT_WINDOW = int(os.getenv("CONTEXT_RECENT_WINDOW", "3"))
CONTEXT_DECAY_PER_TURN = int(os.getenv("CONTEXT_DECAY_PER_TURN", "5"))
CONTEXT_DECAY_PER_TOOL = int(os.getenv("CONTEXT_DECAY_PER_TOOL", "8"))

CONTEXT_SUMMARY_MAX_LEVEL = int(os.getenv("CONTEXT_SUMMARY_MAX_LEVEL", "3"))
CONTEXT_SUMMARY_TURNS_PER_GROUP = int(os.getenv("CONTEXT_SUMMARY_TURNS_PER_GROUP", "5"))

CONTEXT_DYNAMIC_BUDGET_ENABLED = os.getenv("CONTEXT_DYNAMIC_BUDGET_ENABLED", "true").strip().lower() == "true"

CONTEXT_PIPELINE_VERBOSE = os.getenv("CONTEXT_PIPELINE_VERBOSE", "false").strip().lower() == "true"


STATE_BACKEND = os.getenv("STATE_BACKEND", "memory").strip().lower()
STATE_DB_PATH = os.getenv("STATE_DB_PATH", ".runtime/myagent.sqlite3")

# --- Memory embedding & vector search ---
LLM_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-v3")
MEMORY_VECTOR_ENABLED = os.getenv("MEMORY_VECTOR_ENABLED", "true").strip().lower() == "true"
MEMORY_SEARCH_TOP_K = int(os.getenv("MEMORY_SEARCH_TOP_K", "5"))
MEMORY_SEARCH_MIN_SCORE = float(os.getenv("MEMORY_SEARCH_MIN_SCORE", "0.3"))

# --- Memory consolidation ---
MEMORY_CONSOLIDATION_INTERVAL = int(os.getenv("MEMORY_CONSOLIDATION_INTERVAL", "50"))
MEMORY_DEDUP_THRESHOLD = float(os.getenv("MEMORY_DEDUP_THRESHOLD", "0.92"))
MEMORY_IMPORTANCE_DECAY = float(os.getenv("MEMORY_IMPORTANCE_DECAY", "0.1"))
MEMORY_CROSS_SESSION_THRESHOLD = int(os.getenv("MEMORY_CROSS_SESSION_THRESHOLD", "3"))


A2A_PUBLIC_URL = os.getenv("A2A_PUBLIC_URL", "").strip()
A2A_AGENT_VERSION = os.getenv("A2A_AGENT_VERSION", "0.1.0")
A2A_DOCUMENTATION_URL = os.getenv("A2A_DOCUMENTATION_URL")
A2A_ICON_URL = os.getenv("A2A_ICON_URL")
A2A_EXTENDED_CARD_TOKEN = os.getenv("A2A_EXTENDED_CARD_TOKEN")
