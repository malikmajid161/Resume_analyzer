import os
from dotenv import load_dotenv

load_dotenv(override=True)

class Config:
    # --- Security ---
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

    # --- Groq AI ---
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL   = "llama-3.3-70b-versatile"

    # Do not fail at import-time: keep the app usable for non-AI features/local UI.
    # Fail fast when an AI endpoint is actually called.
    # (The AI module and routes will raise a clearer runtime error if needed.)



    # --- File Upload ---
    MAX_FILE_SIZE_MB   = 5
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {"pdf", "docx"}
    UPLOAD_FOLDER      = "/tmp/uploads"

    # --- Scoring Weights ---
    AI_SCORE_WEIGHT      = 0.60
    KEYWORD_SCORE_WEIGHT = 0.40

    # --- AI Prompt ---
    
    MAX_INPUT_CHARS = 28_000
    MAX_RETRY       = 3
    RETRY_DELAY_SEC = 2