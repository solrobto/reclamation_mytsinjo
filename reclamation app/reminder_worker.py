import threading
import time
from datetime import timedelta

from database import get_db
from notifications import send_desktop_notification
from time_utils import now_local, now_local_str

POLL_SECONDS = 30

def _run_loop():
    while True:
        try:
            _process_due_reminders()
        except Exception as exc:
            print(f"[REMINDER_WORKER] error: {exc}")
        time.sleep(POLL_SECONDS)

def _process_due_reminders():
    db = get_db()
    rows = db.execute(
        """
        SELECT id, numero_dossier, nom_client, statut
        FROM reclamations
        WHERE archived = 0
          AND statut != 'TRAITEE'
          AND reminder_auto_at IS NOT NULL
          AND reminder_auto_sent_at IS NULL
          AND reminder_auto_at <= ?
        """
        ,
        (now_local_str(),),
    ).fetchall()

    if not rows:
        db.close()
        return

    now = now_local()
    disabled_until = now + timedelta(minutes=30)

    for row in rows:
        title = "Rappel automatique"
        message = (
            f"La reclamation {row['numero_dossier']} n'a pas encore ete traitee."
        )
        send_desktop_notification(title, message)
        db.execute(
            """
            UPDATE reclamations
            SET reminder_auto_sent_at = ?,
                reminder_last_sent_at = ?,
                reminder_disabled_until = ?
            WHERE id = ?
            """,
            (
                now_local_str(),
                now_local_str(),
                disabled_until.strftime("%Y-%m-%d %H:%M:%S"),
                row["id"],
            ),
        )

    db.commit()
    db.close()

def start_reminder_worker(app=None):
    thread = threading.Thread(target=_run_loop, daemon=True)
    thread.start()
    return thread
