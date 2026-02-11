from datetime import datetime

def now_local():
    return datetime.now()

def now_local_str():
    return now_local().strftime("%Y-%m-%d %H:%M:%S")
