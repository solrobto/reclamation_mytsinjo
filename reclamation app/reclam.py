from database import get_db, is_postgres
from flask import Flask
from flask_login import LoginManager
from config import SECRET_KEY, UPLOAD_FOLDER, MAX_CONTENT_LENGTH
from models import init_db
from auth import auth_bp, load_user
from reclamations import reclamation_bp
from admin import admin_bp
from main import main_bp
from reminder_worker import start_reminder_worker
import os

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)
login_manager.user_loader(load_user)

app.register_blueprint(auth_bp)
app.register_blueprint(reclamation_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(main_bp)

if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        start_reminder_worker(app)
    app.run(debug=True)
