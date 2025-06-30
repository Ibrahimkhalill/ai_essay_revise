# yourapp/management/commands/runscheduler.py
from django.core.management.base import BaseCommand
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone
from datetime import timedelta
from payment.models import Subscription
from django_apscheduler.models import DjangoJobExecution

from django_apscheduler import util


@util.close_old_connections
def delete_old_job_executions(max_age=604_800):  # 7 দিন = 604,800 সেকেন্ড
    DjangoJobExecution.objects.delete_old_job_executions(max_age)
    print("[Scheduler] Old job executions deleted.")

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

class Command(BaseCommand):
    help = 'Run the APScheduler for checking subscriptions'

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        scheduler.add_job(
            check_expired_subscriptions,
            trigger=IntervalTrigger(minutes=1),  # প্রতি ১০ মিনিটে সাবস্ক্রিপশন চেক
            id="check_expired_subscriptions",
            name="Deactivate expired subscriptions and free users",
            replace_existing=True,
        )

        scheduler.add_job(
            delete_old_job_executions,
            trigger=IntervalTrigger(days=7),  # প্রতি ৭ দিনে একবার পুরনো এক্সিকিউশন ডিলিট
            id="delete_old_job_executions",
            name="Delete old APScheduler job executions",
            replace_existing=True,
        )

        scheduler.start()

        self.stdout.write("✅ Subscription Scheduler started. Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            self.stdout.write("🔴 Scheduler stopped.")