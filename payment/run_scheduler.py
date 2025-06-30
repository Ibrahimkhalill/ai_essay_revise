# scheduler.py (অথবা যেকোনো নামের মডিউল)

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone
from datetime import timedelta
from .models import Subscription

scheduler = None  # global scheduler instance

def check_expired_subscriptions():
    now = timezone.now()

    expired = Subscription.objects.filter(is_active=True, end_date__lt=now)
    for subscription in expired:
        subscription.status = 'expired'
        subscription.is_active = False
        subscription.save()

    free_expired = Subscription.objects.filter(
        is_active=True,
        status='free',
        start_date__lt=now - timedelta(days=7)
    )
    free_expired.update(is_active=False)

    print(f"[Scheduler] Expired: {expired.count()}, Free expired: {free_expired.count()}")

def start_scheduler():
    global scheduler
    if scheduler and scheduler.running:
        print("Scheduler already running")
        return

    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")

    scheduler.add_job(
        check_expired_subscriptions,
        trigger=IntervalTrigger(minutes=1),
        id="check_expired_subscriptions",
        name="Deactivate expired subscriptions and free users",
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduler started")
