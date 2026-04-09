import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-5.4-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))


MAX_STEPS = int(os.getenv("MAX_STEPS", "5"))