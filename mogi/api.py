
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db import transaction, models
from django.contrib.auth.decorators import login_required
from .models import Track, Mogi, Race, canonicalize_track, slug_for_track

def _current_mogi(user):
    m = Mogi.objects.filter(owner=user, finalized=False).order_by("created_at").first()
    return m or Mogi.objects.create(owner=user)

def _get_or_create_track(raw_name: str) -> Track:
    canon = canonicalize_track(raw_name)
    track, _ = Track.objects.get_or_create(name=canon, defaults={"slug": slug_for_track(canon)})
    return track

@login_required
@require_POST
def add_race(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        track_raw = payload.get("track")
        position = int(payload.get("position"))
        if not track_raw or position < 1 or position > 12:
            return HttpResponseBadRequest("Invalid track/position")
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    with transaction.atomic():
        mogi = _current_mogi(request.user)
        next_index = (mogi.races.aggregate(mx=models.Max("index"))["mx"] or 0) + 1
        if next_index > 12:
            return HttpResponseBadRequest("Mogi already has 12 races")
        track = _get_or_create_track(track_raw)
        Race.objects.create(mogi=mogi, track=track, index=next_index, position=position)
        return JsonResponse({"ok": True, "mogi_id": mogi.id, "next_index": next_index})

@login_required
@require_POST
def undo_last(request):
    mogi = _current_mogi(request.user)
    last = mogi.races.order_by("-index").first()
    if not last:
        return JsonResponse({"ok": False, "error": "No races to undo"})
    last.delete()
    return JsonResponse({"ok": True})

@login_required
@require_POST
def reset_current(request):
    mogi = _current_mogi(request.user)
    mogi.races.all().delete()
    return JsonResponse({"ok": True})

@login_required
@require_POST
def finalize_current(request):
    mogi = _current_mogi(request.user)
    if mogi.race_count != 12:
        return HttpResponseBadRequest("Need 12 races to finalize")
    mogi.finalized = True
    mogi.save(update_fields=["finalized"])
    return JsonResponse({"ok": True, "mogi_id": mogi.id})

@login_required
def export_data(request):
    user_mogis = list(Mogi.objects.filter(owner=request.user).values("id", "created_at", "finalized", "note"))
    races = list(Race.objects.filter(mogi__owner=request.user).values("id", "mogi_id", "track_id", "index", "position", "points"))
    tracks = list(Track.objects.values("id", "name", "slug"))
    return JsonResponse({"tracks": tracks, "mogis": user_mogis, "races": races})

@login_required
@require_POST
def import_data(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    tracks = payload.get("tracks", [])
    mogis = payload.get("mogis", [])
    races = payload.get("races", [])

    with transaction.atomic():
        id_map_track = {}
        for t in tracks:
            canon = canonicalize_track(t["name"])
            trk, _ = Track.objects.get_or_create(name=canon, defaults={"slug": slug_for_track(canon)})
            id_map_track[t["id"]] = trk.id

        id_map_mogi = {}
        for m in mogis:
            obj = Mogi.objects.create(owner=request.user, finalized=m["finalized"], note=m.get("note", ""))
            id_map_mogi[m["id"]] = obj.id

        for r in races:
            Race.objects.create(
                mogi_id=id_map_mogi[r["mogi_id"]],
                track_id=id_map_track[r["track_id"]],
                index=r["index"],
                position=r["position"],
                points=r["points"],
            )
    return JsonResponse({"ok": True})
