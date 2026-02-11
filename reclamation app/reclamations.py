import os
import math
from datetime import datetime, timedelta
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, current_app, send_from_directory, abort, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from database import get_db, is_postgres
from auth import role_required
from config import ALLOWED_EXTENSIONS
from notifications import send_desktop_notification
from time_utils import now_local, now_local_str

reclamation_bp = Blueprint("reclamation", __name__)

def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

@reclamation_bp.route("/notifications/user", methods=["GET"])
@login_required
def user_notifications():
    if current_user.role != "agent":
        return jsonify({"updates": [], "server_time": now_local_str()})

    since = request.args.get("since", "").strip()
    db = get_db()

    if since:
        rows = db.execute(
            """
            SELECT h.reclamation_id, h.nouveau_statut, h.created_at, r.numero_dossier
            FROM historique_statut h
            JOIN reclamations r ON r.id = h.reclamation_id
            WHERE r.user_id = ?
              AND h.created_at > ?
            ORDER BY h.created_at ASC
            """,
            (current_user.id, since),
        ).fetchall()
    else:
        rows = []

    db.close()
    updates = [
        {
            "reclamation_id": row["reclamation_id"],
            "nouveau_statut": row["nouveau_statut"],
            "created_at": row["created_at"],
            "numero_dossier": row["numero_dossier"],
        }
        for row in rows
    ]
    return jsonify({"updates": updates, "server_time": now_local_str()})

@reclamation_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    db = get_db()
    types = db.execute(
        "SELECT id, libelle FROM types_reclamation WHERE actif = 1 ORDER BY libelle"
    ).fetchall()
    bureaux = db.execute(
        "SELECT id, code_bureau, nom_bureau FROM bureaux ORDER BY nom_bureau"
    ).fetchall()

    statut = request.args.get("statut") or ""
    bureau_id = request.args.get("bureau_id") or ""
    type_id = request.args.get("type_id") or ""
    search = request.args.get("search") or ""
    archived = request.args.get("archived") == "1"

    filters = []
    params = []

    if current_user.role == "agent":
        filters.append("r.user_id = ?")
        params.append(current_user.id)
    if statut:
        filters.append("r.statut = ?")
        params.append(statut)
    if bureau_id:
        filters.append("r.bureau_id = ?")
        params.append(bureau_id)
    if type_id:
        filters.append("r.type_id = ?")
        params.append(type_id)
    if search:
        filters.append("(r.numero_dossier LIKE ? OR r.numero_compte LIKE ? OR r.nom_client LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    filters.append("r.archived = ?")
    params.append(1 if archived else 0)
    where_clause = "WHERE " + " AND ".join(filters) if filters else "WHERE r.archived = ?"

    query = f"""
        SELECT r.id, r.numero_dossier, r.numero_compte, r.nom_client, r.motif,
               r.statut, r.created_at, b.nom_bureau, t.libelle, u.username
        FROM reclamations r
        LEFT JOIN bureaux b ON b.id = r.bureau_id
        LEFT JOIN types_reclamation t ON t.id = r.type_id
        LEFT JOIN users u ON u.id = r.user_id
        {where_clause}
        ORDER BY r.created_at DESC
        """

    reclamations = db.execute(query, params).fetchall()
    db.close()

    return render_template(
        "dashboard.html",
        reclamations=reclamations,
        types=types,
        bureaux=bureaux,
        statut=statut,
        bureau_id=bureau_id,
        type_id=type_id,
        search=search,
        archived=archived,
    )

@reclamation_bp.route("/reclamation/new", methods=["GET", "POST"])
@login_required
@role_required("agent")
def new_reclamation():
    error = None
    db = get_db()
    types = db.execute(
        "SELECT id, libelle FROM types_reclamation WHERE actif = 1 ORDER BY libelle"
    ).fetchall()
    db.close()

    if request.method == "POST":
        numero_compte = request.form.get("numero_compte", "").strip()
        nom_client = request.form.get("nom_client", "").strip()
        type_id = request.form.get("type_id") or None
        ancienne_valeur = request.form.get("ancienne_valeur", "").strip()
        nouvelle_valeur = request.form.get("nouvelle_valeur", "").strip()
        motif = request.form.get("motif", "").strip()

        if not numero_compte or not nom_client or not type_id:
            error = "Veuillez remplir tous les champs."
        else:
            if not motif:
                db = get_db()
                type_row = db.execute(
                    "SELECT code FROM types_reclamation WHERE id = ?",
                    (type_id,),
                ).fetchone()
                db.close()
                if type_row and type_row["code"] == "AUTRE":
                    error = "Le motif est obligatoire pour le type Autre."
                else:
                    motif = ""
            if error:
                return render_template(
                    "reclamation_form.html",
                    error=error,
                    types=types,
                    numero_compte=numero_compte,
                    nom_client=nom_client,
                    type_id=type_id,
                    ancienne_valeur=ancienne_valeur,
                    nouvelle_valeur=nouvelle_valeur,
                    motif=motif,
                )
            db = get_db()
            if is_postgres():
                cur = db.execute(
                    """
                    INSERT INTO reclamations (
                        user_id, bureau_id, type_id, numero_compte,
                        nom_client, ancienne_valeur, nouvelle_valeur, motif
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                    """,
                    (
                        current_user.id,
                        current_user.bureau_id,
                        type_id,
                        numero_compte,
                        nom_client,
                        ancienne_valeur,
                        nouvelle_valeur,
                        motif,
                    ),
                )
                reclamation_id = cur.fetchone()["id"]
            else:
                cur = db.execute(
                    """
                    INSERT INTO reclamations (
                        user_id, bureau_id, type_id, numero_compte,
                        nom_client, ancienne_valeur, nouvelle_valeur, motif
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_user.id,
                        current_user.bureau_id,
                        type_id,
                        numero_compte,
                        nom_client,
                        ancienne_valeur,
                        nouvelle_valeur,
                        motif,
                    ),
                )
                reclamation_id = cur.lastrowid
            numero_dossier = f"REC-{now_local().strftime('%Y%m%d')}-{reclamation_id:05d}"
            db.execute(
                "UPDATE reclamations SET numero_dossier = ? WHERE id = ?",
                (numero_dossier, reclamation_id),
            )
            created_at = now_local_str()
            db.execute(
                "UPDATE reclamations SET created_at = ? WHERE id = ?",
                (created_at, reclamation_id),
            )
            db.execute(
                """
                INSERT INTO historique_statut (reclamation_id, ancien_statut, nouveau_statut, observation, user_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (reclamation_id, None, "EN_ATTENTE", "Creation", current_user.id, created_at),
            )

            files = request.files.getlist("pieces")
            for f in files:
                if not f or f.filename == "":
                    continue
                if not _allowed_file(f.filename):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                f.save(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name))
                db.execute(
                    """
                    INSERT INTO pieces_jointes (reclamation_id, filename, original_name, uploaded_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (reclamation_id, unique_name, safe_name, created_at),
                )

            db.commit()
            db.close()
            return redirect(url_for("reclamation.dashboard"))

    return render_template(
        "reclamation_form.html",
        error=error,
        types=types,
        numero_compte=request.form.get("numero_compte", ""),
        nom_client=request.form.get("nom_client", ""),
        type_id=request.form.get("type_id", ""),
        ancienne_valeur=request.form.get("ancienne_valeur", ""),
        nouvelle_valeur=request.form.get("nouvelle_valeur", ""),
        motif=request.form.get("motif", ""),
    )

@reclamation_bp.route("/reclamation/<int:reclamation_id>", methods=["GET"])
@login_required
def view_reclamation(reclamation_id):
    db = get_db()
    reclamation = db.execute(
        """
        SELECT r.*, b.nom_bureau, t.libelle, u.username
        FROM reclamations r
        LEFT JOIN bureaux b ON b.id = r.bureau_id
        LEFT JOIN types_reclamation t ON t.id = r.type_id
        LEFT JOIN users u ON u.id = r.user_id
        WHERE r.id = ?
        """,
        (reclamation_id,),
    ).fetchone()
    if not reclamation:
        db.close()
        abort(404)

    if current_user.role == "agent" and str(reclamation["user_id"]) != str(current_user.id):
        db.close()
        abort(403)

    pieces = db.execute(
        "SELECT id, filename, original_name, uploaded_at FROM pieces_jointes WHERE reclamation_id = ?",
        (reclamation_id,),
    ).fetchall()
    historique = db.execute(
        """
        SELECT h.*, u.username
        FROM historique_statut h
        LEFT JOIN users u ON u.id = h.user_id
        WHERE h.reclamation_id = ?
        ORDER BY h.created_at DESC
        """,
        (reclamation_id,),
    ).fetchall()
    db.close()

    now = now_local()
    disabled_until = _parse_dt(reclamation["reminder_disabled_until"])
    reminder_disabled = bool(disabled_until and disabled_until > now)
    reminder_remaining_min = None
    if reminder_disabled:
        seconds = max(0, int((disabled_until - now).total_seconds()))
        reminder_remaining_min = max(1, math.ceil(seconds / 60))

    return render_template(
        "reclamation_detail.html",
        reclamation=reclamation,
        pieces=pieces,
        historique=historique,
        reminder_disabled=reminder_disabled,
        reminder_remaining_min=reminder_remaining_min,
    )

@reclamation_bp.route("/reclamation/<int:reclamation_id>/reminder", methods=["POST"])
@login_required
def send_reminder(reclamation_id):
    db = get_db()
    reclamation = db.execute(
        """
        SELECT id, numero_dossier, nom_client, statut, user_id, reminder_disabled_until
        FROM reclamations
        WHERE id = ?
        """,
        (reclamation_id,),
    ).fetchone()
    if not reclamation:
        db.close()
        abort(404)

    if current_user.role == "agent" and str(reclamation["user_id"]) != str(current_user.id):
        db.close()
        abort(403)

    if reclamation["statut"] == "TRAITEE":
        db.close()
        flash("Cette reclamation est deja traitee.", "info")
        return redirect(url_for("reclamation.view_reclamation", reclamation_id=reclamation_id))

    now = now_local()
    disabled_until = _parse_dt(reclamation["reminder_disabled_until"])
    if disabled_until and disabled_until > now:
        remaining = max(1, math.ceil((disabled_until - now).total_seconds() / 60))
        db.close()
        flash(f"Rappel indisponible. Reessayez dans {remaining} min.", "warning")
        return redirect(url_for("reclamation.view_reclamation", reclamation_id=reclamation_id))

    title = "Rappel reclamation"
    message = f"La reclamation {reclamation['numero_dossier']} n'a pas encore ete traitee."
    send_desktop_notification(title, message)

    disabled_until = now + timedelta(minutes=30)
    auto_at = now + timedelta(hours=1)
    db.execute(
        """
        UPDATE reclamations
        SET reminder_requested_at = ?,
            reminder_disabled_until = ?,
            reminder_auto_at = ?,
            reminder_auto_sent_at = NULL,
            reminder_last_sent_at = ?
        WHERE id = ?
        """,
        (
            now_local_str(),
            disabled_until.strftime("%Y-%m-%d %H:%M:%S"),
            auto_at.strftime("%Y-%m-%d %H:%M:%S"),
            now_local_str(),
            reclamation_id,
        ),
    )
    db.commit()
    db.close()
    flash("Rappel envoye. Un rappel automatique sera lance dans 1 heure si non traitee.", "success")
    return redirect(url_for("reclamation.view_reclamation", reclamation_id=reclamation_id))

@reclamation_bp.route("/reclamation/<int:reclamation_id>/status", methods=["POST"])
@login_required
@role_required("supervisor", "admin")
def update_status(reclamation_id):
    new_status = request.form.get("statut", "").strip()
    observation = request.form.get("observation", "").strip()

    if new_status not in ["EN_ATTENTE", "EN_COURS", "TRAITEE", "REJETEE"]:
        abort(400)

    db = get_db()
    current = db.execute(
        "SELECT statut, numero_dossier, user_id FROM reclamations WHERE id = ?",
        (reclamation_id,),
    ).fetchone()
    if not current:
        db.close()
        abort(404)

    if new_status == "TRAITEE":
        db.execute(
            """
            UPDATE reclamations
            SET statut = ?, observation = ?, updated_at = ?,
                reminder_auto_at = NULL,
                reminder_auto_sent_at = NULL,
                reminder_disabled_until = NULL
            WHERE id = ?
            """,
            (new_status, observation, now_local_str(), reclamation_id),
        )
    else:
        db.execute(
            """
            UPDATE reclamations
            SET statut = ?, observation = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, observation, now_local_str(), reclamation_id),
        )
    db.execute(
        """
        INSERT INTO historique_statut (reclamation_id, ancien_statut, nouveau_statut, observation, user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (reclamation_id, current["statut"], new_status, observation, current_user.id, now_local_str()),
    )
    # Notify requester (desktop notification on server machine)
    try:
        requester = db.execute(
            "SELECT username, prenom, nom FROM users WHERE id = ?",
            (current["user_id"],),
        ).fetchone()
        requester_name = None
        if requester:
            requester_name = " ".join(
                part for part in [requester["prenom"], requester["nom"]] if part
            ) or requester["username"]
        dossier = current["numero_dossier"] or f"ID {reclamation_id}"
        title = "Statut de reclamation mis a jour"
        if requester_name:
            message = f"{requester_name}: {dossier} -> {new_status}"
        else:
            message = f"{dossier} -> {new_status}"
        send_desktop_notification(title, message)
    except Exception:
        pass
    db.commit()
    db.close()
    return redirect(url_for("reclamation.view_reclamation", reclamation_id=reclamation_id))

@reclamation_bp.route("/reclamation/<int:reclamation_id>/archive", methods=["POST"])
@login_required
@role_required("supervisor", "admin")
def archive_reclamation(reclamation_id):
    db = get_db()
    row = db.execute(
        "SELECT statut FROM reclamations WHERE id = ?",
        (reclamation_id,),
    ).fetchone()
    if not row:
        db.close()
        abort(404)
    if row["statut"] != "TRAITEE":
        db.close()
        abort(400)

    db.execute(
        "UPDATE reclamations SET archived = 1, updated_at = ? WHERE id = ?",
        (now_local_str(), reclamation_id),
    )
    db.execute(
        """
        INSERT INTO historique_statut (reclamation_id, ancien_statut, nouveau_statut, observation, user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (reclamation_id, "TRAITEE", "ARCHIVEE", "Archivage", current_user.id, now_local_str()),
    )
    db.commit()
    db.close()
    return redirect(url_for("reclamation.dashboard"))

@reclamation_bp.route("/reclamation/<int:reclamation_id>/unarchive", methods=["POST"])
@login_required
@role_required("supervisor", "admin")
def unarchive_reclamation(reclamation_id):
    db = get_db()
    row = db.execute(
        "SELECT archived FROM reclamations WHERE id = ?",
        (reclamation_id,),
    ).fetchone()
    if not row:
        db.close()
        abort(404)
    if row["archived"] != 1:
        db.close()
        abort(400)

    db.execute(
        "UPDATE reclamations SET archived = 0, updated_at = ? WHERE id = ?",
        (now_local_str(), reclamation_id),
    )
    db.execute(
        """
        INSERT INTO historique_statut (reclamation_id, ancien_statut, nouveau_statut, observation, user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (reclamation_id, "ARCHIVEE", "RESTAUREE", "Restauration", current_user.id, now_local_str()),
    )
    db.commit()
    db.close()
    return redirect(url_for("reclamation.dashboard", archived=1))

@reclamation_bp.route("/uploads/<path:filename>", methods=["GET"])
@login_required
def download_piece(filename):
    db = get_db()
    piece = db.execute(
        "SELECT reclamation_id FROM pieces_jointes WHERE filename = ?",
        (filename,),
    ).fetchone()
    if not piece:
        db.close()
        abort(404)

    reclamation = db.execute(
        "SELECT user_id FROM reclamations WHERE id = ?",
        (piece["reclamation_id"],),
    ).fetchone()
    db.close()

    if not reclamation:
        abort(404)
    if current_user.role == "agent" and str(reclamation["user_id"]) != str(current_user.id):
        abort(403)

    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, as_attachment=True)
