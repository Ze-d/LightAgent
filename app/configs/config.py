import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-5.4-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))


MAX_STEPS = int(os.getenv("MAX_STEPS", "5"))


A2A_PUBLIC_URL = os.getenv("A2A_PUBLIC_URL", "").strip()
A2A_AGENT_VERSION = os.getenv("A2A_AGENT_VERSION", "0.1.0")
A2A_DOCUMENTATION_URL = os.getenv("A2A_DOCUMENTATION_URL")
A2A_ICON_URL = os.getenv("A2A_ICON_URL")
A2A_EXTENDED_CARD_TOKEN = os.getenv("A2A_EXTENDED_CARD_TOKEN")
