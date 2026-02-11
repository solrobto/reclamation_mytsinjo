import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = "MYTSINJO_SECRET_KEY"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE_PATH = os.path.join(BASE_DIR, "reclamation.db")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024
