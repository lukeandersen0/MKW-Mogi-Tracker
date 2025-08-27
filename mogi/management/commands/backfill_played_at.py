from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from mogi.models import Mogi

User = get_user_model()

class Command(BaseCommand):
    help = "Backfill Mogi.played_at in chronological order per user (oldest -> newest)."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Only backfill for this user (optional)")

    def handle(self, *args, **opts):
        qs = Mogi.objects.all().order_by("id")
        if opts.get("username"):
            qs = qs.filter(owner__username=opts["username"])
        # space them 1 minute apart to guarantee strict ordering
        count = 0
        now = timezone.now()
        for owner_id in qs.values_list("owner_id", flat=True).distinct():
            rows = list(qs.filter(owner_id=owner_id))
            base = now - timedelta(days=365)  # any stable base in the past
            for i, m in enumerate(rows):
                m.played_at = base + timedelta(minutes=i)
            Mogi.objects.bulk_update(rows, ["played_at"])
            count += len(rows)
        self.stdout.write(self.style.SUCCESS(f"Backfilled played_at on {count} mogis."))
