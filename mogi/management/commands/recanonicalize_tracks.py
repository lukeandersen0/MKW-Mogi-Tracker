
from django.core.management.base import BaseCommand
from django.db import transaction
from mogi.models import Track, Race, canonicalize_track, slug_for_track

class Command(BaseCommand):
    help = "Re-canonicalize tracks and merge duplicates (fixes multiple Bowser's Castle variants)."

    def handle(self, *args, **kwargs):
        with transaction.atomic():
            canon_map = {}
            for tr in Track.objects.all():
                canon = canonicalize_track(tr.name)
                if canon not in canon_map:
                    tr.name = canon
                    tr.slug = slug_for_track(canon)
                    tr.save(update_fields=["name", "slug"])
                    canon_map[canon] = tr
                else:
                    target = canon_map[canon]
                    Race.objects.filter(track=tr).update(track=target)
                    tr.delete()
        self.stdout.write(self.style.SUCCESS("Tracks canonicalized and duplicates merged."))
