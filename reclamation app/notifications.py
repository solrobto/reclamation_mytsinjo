try:
    from win10toast import ToastNotifier
except Exception:  # pragma: no cover - optional dependency
    ToastNotifier = None

_notifier = None

def send_desktop_notification(title, message):
    global _notifier
    if ToastNotifier is None:
        # Fallback: no Windows notifier installed
        print(f"[NOTIFY] {title} - {message}")
        return
    if _notifier is None:
        _notifier = ToastNotifier()
    _notifier.show_toast(title, message, duration=8, threaded=True)
