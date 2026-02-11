from flask import Blueprint, render_template, request, redirect, url_for, abort, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from database import get_db
from auth import role_required
from time_utils import now_local_str

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin", methods=["GET"])
@login_required
@role_required("admin")
def admin_dashboard():
    db = get_db()
    counts = {
        "users": db.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"],
        "bureaux": db.execute("SELECT COUNT(*) AS cnt FROM bureaux").fetchone()["cnt"],
        "types": db.execute("SELECT COUNT(*) AS cnt FROM types_reclamation").fetchone()["cnt"],
        "reclamations": db.execute("SELECT COUNT(*) AS cnt FROM reclamations").fetchone()["cnt"],
        "pending": db.execute("SELECT COUNT(*) AS cnt FROM users WHERE active = 0").fetchone()["cnt"],
    }
    db.close()
    return render_template("admin_dashboard.html", counts=counts)

@admin_bp.route("/admin/notifications", methods=["GET"])
@login_required
@role_required("admin", "supervisor")
def notifications():
    db = get_db()
    pending_reclamations = db.execute(
        "SELECT COUNT(*) AS cnt FROM reclamations WHERE statut = 'EN_ATTENTE' AND archived = 0"
    ).fetchone()["cnt"]
    if current_user.role == "admin":
        pending_users = db.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE active = 0"
        ).fetchone()["cnt"]
    else:
        pending_users = 0
    db.close()
    return jsonify(
        {
            "pending_reclamations": pending_reclamations,
            "pending_users": pending_users,
        }
    )

@admin_bp.route("/admin/users", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_users():
    db = get_db()
    bureaux = db.execute("SELECT id, code_bureau, nom_bureau FROM bureaux ORDER BY nom_bureau").fetchall()
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "agent").strip() or "agent"
        bureau_id = request.form.get("bureau_id") or None
        prenom = request.form.get("prenom", "").strip()
        nom = request.form.get("nom", "").strip()
        matricule = request.form.get("matricule", "").strip()
        if not username or not password or not prenom or not nom or not matricule:
            error = "Champs manquants."
        else:
            existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                error = "Utilisateur existe deja."
            else:
                db.execute(
                    """
                    INSERT INTO users (username, password, role, bureau_id, prenom, nom, matricule, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (username, generate_password_hash(password), role, bureau_id, prenom, nom, matricule, now_local_str()),
                )
                db.commit()

    users = db.execute(
        """
        SELECT u.id, u.username, u.role, u.active, u.bureau_id, u.prenom, u.nom, u.matricule, b.nom_bureau
        FROM users u
        LEFT JOIN bureaux b ON b.id = u.bureau_id
        ORDER BY u.username
        """
    ).fetchall()
    db.close()
    return render_template("admin_users.html", users=users, bureaux=bureaux, error=error)

@admin_bp.route("/admin/users/<int:user_id>/update", methods=["POST"])
@login_required
@role_required("admin")
def update_user(user_id):
    role = request.form.get("role", "agent")
    active = request.form.get("active") == "1"
    bureau_id = request.form.get("bureau_id") or None
    db = get_db()
    db.execute(
        "UPDATE users SET role = ?, active = ?, bureau_id = ? WHERE id = ?",
        (role, 1 if active else 0, bureau_id, user_id),
    )
    db.commit()
    db.close()
    return redirect(url_for("admin.manage_users"))

@admin_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_user(user_id):
    db = get_db()
    # Soft delete: deactivate user to preserve history
    db.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
    db.commit()
    db.close()
    return redirect(url_for("admin.manage_users"))

@admin_bp.route("/admin/pending", methods=["GET", "POST"])
@login_required
@role_required("admin")
def pending_users():
    db = get_db()
    if request.method == "POST":
        user_id = request.form.get("user_id")
        action = request.form.get("action")
        if user_id and action in ["approve", "reject"]:
            if action == "approve":
                db.execute("UPDATE users SET active = 1 WHERE id = ?", (user_id,))
            else:
                db.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
            db.commit()

    pending = db.execute(
        """
        SELECT u.id, u.username, u.prenom, u.nom, u.matricule, u.role, b.nom_bureau
        FROM users u
        LEFT JOIN bureaux b ON b.id = u.bureau_id
        WHERE u.active = 0
        ORDER BY u.created_at DESC
        """
    ).fetchall()
    db.close()
    return render_template("admin_pending.html", pending=pending)

@admin_bp.route("/admin/bureaux", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_bureaux():
    db = get_db()
    if request.method == "POST":
        code = request.form.get("code_bureau", "").strip()
        nom = request.form.get("nom_bureau", "").strip()
        province = None
        if code:
            province = {
                "1": "ANTANANARIVO",
                "2": "ANTSIRANANA",
                "3": "FIANARANTSOA",
                "4": "MAHAJANGA",
                "5": "TOAMASINA",
                "6": "TOLIARA",
            }.get(code[0])
        if code and nom:
            db.execute(
                "INSERT INTO bureaux (code_bureau, nom_bureau, province) VALUES (?, ?, ?)",
                (code, nom, province),
            )
            db.commit()

    bureaux = db.execute(
        "SELECT id, code_bureau, nom_bureau, province FROM bureaux ORDER BY province, nom_bureau"
    ).fetchall()
    db.close()
    return render_template("admin_bureaux.html", bureaux=bureaux)

@admin_bp.route("/admin/types", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_types():
    db = get_db()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        libelle = request.form.get("libelle", "").strip()
        if code and libelle:
            db.execute(
                "INSERT INTO types_reclamation (code, libelle) VALUES (?, ?)",
                (code, libelle),
            )
            db.commit()

    types = db.execute(
        "SELECT id, code, libelle, actif FROM types_reclamation ORDER BY libelle"
    ).fetchall()
    db.close()
    return render_template("admin_types.html", types=types)

@admin_bp.route("/admin/types/<int:type_id>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def toggle_type(type_id):
    db = get_db()
    row = db.execute(
        "SELECT actif FROM types_reclamation WHERE id = ?",
        (type_id,),
    ).fetchone()
    if not row:
        db.close()
        abort(404)
    new_val = 0 if row["actif"] == 1 else 1
    db.execute("UPDATE types_reclamation SET actif = ? WHERE id = ?", (new_val, type_id))
    db.commit()
    db.close()
    return redirect(url_for("admin.manage_types"))
