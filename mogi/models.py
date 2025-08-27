from django.utils import timezone

from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.contrib.auth.models import User

# ---------- Canonicalization ----------

CANON_MAP = {
    "bowser castle": "bowser's castle",
    "bowsers castle": "bowser's castle",
    "bowser’s castle": "bowser's castle",
    "bowser castle 1": "bowser's castle",
    "bowser castle 2": "bowser's castle",
    "bowser castle 3": "bowser's castle",
    "bowser castle 4": "bowser's castle",
    "bowser's castle 1": "bowser's castle",
    "bowser's castle 2": "bowser's castle",
    "bowser's castle 3": "bowser's castle",
    "bowser's castle 4": "bowser's castle",
    "bc": "bowser's castle",
}

def canonicalize_track(raw: str) -> str:
    if not raw:
        return ""
    name = " ".join(raw.strip().lower().replace("’", "'").split())
    return CANON_MAP.get(name, name)

def slug_for_track(canon_name: str) -> str:
    return slugify(canon_name)

# ---------- Models ----------

class Track(models.Model):
    # Global track catalog; shared across users (intentional)
    name = models.CharField(max_length=100, unique=True)  # canonical lower-case
    slug = models.SlugField(max_length=110, unique=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        canon = canonicalize_track(self.name)
        self.name = canon
        self.slug = slug_for_track(canon)
        super().save(*args, **kwargs)

    def display_name(self) -> str:
        dn = self.name.title().replace("'S ", "'s ").replace("S' ", "s' ")
        return dn

    def __str__(self):
        return self.display_name()

DEFAULT_POINTS = {
    1: 15, 2: 12, 3: 10, 4: 9, 5: 8, 6: 7,
    7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1
}

class Mogi(models.Model):
    owner = models.ForeignKey(User, related_name="mogis", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    finalized = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True, default="")
    played_at = models.DateTimeField(default=timezone.now, db_index=True)
    # future sharing:
    # shared_with = models.ManyToManyField(User, blank=True, related_name="mogis_shared")

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["owner", "created_at"])]

    @property
    def race_count(self) -> int:
        return self.races.count()

    @property
    def is_complete(self) -> bool:
        return self.race_count == 12

    @property
    def total_points(self) -> int:
        return sum(r.points for r in self.races.all())

    @property
    def avg_finish(self) -> float:
        qs = self.races.all()
        return round(sum(r.position for r in qs) / qs.count(), 2) if qs.exists() else 0.0

    def __str__(self):
        return f"Mogi ({self.created_at:%Y-%m-%d %H:%M})"

class Race(models.Model):
    mogi = models.ForeignKey(Mogi, related_name="races", on_delete=models.CASCADE)
    track = models.ForeignKey(Track, related_name="races", on_delete=models.PROTECT)
    index = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Race number within the mogi (1..12)"
    )
    position = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    points = models.IntegerField(default=0)

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["mogi", "index"], name="unique_race_index_per_mogi")
        ]

    def save(self, *args, **kwargs):
        if not self.points:
            self.points = DEFAULT_POINTS.get(self.position, 0)
        super().save(*args, **kwargs)

    @property
    def css_class(self):
        # used by templates so we don't need {% if r.position <= 3 %} etc.
        if self.position <= 3:
            return "good"
        if self.position >= 10:
            return "bad"
        return ""


    def __str__(self):
        return f"{self.mogi_id} • {self.track.display_name()} • #{self.index} • P{self.position}"
