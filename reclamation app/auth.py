from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
from time_utils import now_local_str

auth_bp = Blueprint("auth", __name__)

class User(UserMixin):
    def __init__(self, id, username, role, bureau_id, prenom, nom, matricule):
        self.id = str(id)
        self.username = username
        self.role = role
        self.bureau_id = bureau_id
        self.prenom = prenom
        self.nom = nom
        self.matricule = matricule

def load_user(user_id):
    db = get_db()
    user = db.execute(
        "SELECT id, username, role, bureau_id, prenom, nom, matricule FROM users WHERE id = ? AND active = 1",
        (user_id,),
    ).fetchone()
    db.close()
    if not user:
        return None
    return User(user["id"], user["username"], user["role"], user["bureau_id"], user["prenom"], user["nom"], user["matricule"])

def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("reclamation.dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            """
            SELECT id, username, password, role, bureau_id, active, prenom, nom, matricule
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        db.close()

        if user and user["active"] == 1 and check_password_hash(user["password"], password):
            login_user(
                User(
                    user["id"],
                    user["username"],
                    user["role"],
                    user["bureau_id"],
                    user["prenom"],
                    user["nom"],
                    user["matricule"],
                )
            )
            return redirect(url_for("reclamation.dashboard"))

        error = "Identifiants invalides."

    return render_template("login.html", error=error)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    error = None
    db = get_db()
    bureaux = db.execute("SELECT id, code_bureau, nom_bureau FROM bureaux").fetchall()
    admin_exists = db.execute(
        "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
    ).fetchone()
    db.close()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        bureau_id = request.form.get("bureau_id") or None
        prenom = request.form.get("prenom", "").strip()
        nom = request.form.get("nom", "").strip()
        matricule = request.form.get("matricule", "").strip()

        if not admin_exists:
            role = request.form.get("role", "admin").strip() or "admin"
        else:
            role = "agent"

        if not username or not password or not prenom or not nom or not matricule:
            error = "Veuillez remplir tous les champs."
        else:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if existing:
                error = "Ce nom d'utilisateur existe deja."
            else:
                active = 1 if not admin_exists else 0
                db.execute(
                    """
                    INSERT INTO users (username, password, role, bureau_id, prenom, nom, matricule, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (username, generate_password_hash(password), role, bureau_id, prenom, nom, matricule, active, now_local_str()),
                )
                db.commit()
                db.close()
                if active == 1:
                    flash("Compte cree. Vous pouvez vous connecter.", "success")
                else:
                    flash("Compte cree. Attente validation admin.", "warning")
                return redirect(url_for("auth.login"))
            db.close()

    return render_template(
        "register.html",
        error=error,
        bureaux=bureaux,
        allow_role=not admin_exists,
    )

@auth_bp.route("/logout", methods=["GET"])
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    error = None
    if request.method == "POST":
        prenom = request.form.get("prenom", "").strip()
        nom = request.form.get("nom", "").strip()
        matricule = request.form.get("matricule", "").strip()
        if not prenom or not nom or not matricule:
            error = "Veuillez remplir tous les champs."
        else:
            db = get_db()
            db.execute(
                """
                UPDATE users
                SET prenom = ?, nom = ?, matricule = ?
                WHERE id = ?
                """,
                (prenom, nom, matricule, current_user.id),
            )
            db.commit()
            db.close()
            flash("Profil mis a jour.", "success")
            return redirect(url_for("auth.profile"))

    return render_template("profile.html", error=error)
