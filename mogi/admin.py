
from django.contrib import admin
from .models import Track, Mogi, Race

@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ("display_name", "name", "slug")
    search_fields = ("name", "slug")

class RaceInline(admin.TabularInline):
    model = Race
    extra = 0

@admin.register(Mogi)
class MogiAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "created_at", "finalized", "race_count", "total_points", "avg_finish", "note")
    inlines = [RaceInline]
    ordering = ("owner", "created_at")
    list_filter = ("finalized", "owner")

@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ("mogi", "index", "track", "position", "points")
    list_filter = ("track", "mogi__finalized", "mogi__owner")
    search_fields = ("track__name",)
    ordering = ("mogi__created_at", "index")
