from django.utils import timezone
from datetime import timedelta


def is_presence_locked(event):
    lock_time = event.date + timedelta(hours=12)
    return (timezone.now() >= lock_time, lock_time)
