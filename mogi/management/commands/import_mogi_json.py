import json
from collections import defaultdict
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from mogi.models import Track, Mogi, Race, canonicalize_track, slug_for_track

User = get_user_model()


def ensure_track_id(name: str) -> int:
    """Canonicalize and upsert a Track; return its id."""
    canon = canonicalize_track(name or "")
    if not canon:
        raise ValueError("Empty track name")
    trk, _ = Track.objects.get_or_create(name=canon, defaults={"slug": slug_for_track(canon)})
    return trk.id


class Command(BaseCommand):
    help = (
        "Import mogi data for a user from JSON (auto-detects multiple formats).\n"
        "Supported shapes:\n"
        "  A) {'tracks':[],'mogis':[],'races':[]} with id references\n"
        "  B) {'mogis':[{'finalized':bool,'note':?, 'races':[{'track':str,'position':int,'index':int?}, ...]}]}\n"
        "  C) [ ... same as B but the list itself ]\n"
        "  D) {'history': [ {'track':str, 'position':int, 'index'?:int, ...}, ... ]}\n"
        "  E) A flat list of races: [ {'track':str, 'position':int, 'index'?:int, ...}, ... ]\n"
        "\n"
        "For D/E (flat race history), races are chunked into mogis of 12 (in order)."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username who will own the imported data")
        parser.add_argument("json_path", help="Path to export JSON file")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and show what would be imported without saving"
        )

    # -------------- Parsers for different shapes --------------

    def parse_format_A(self, data):
        """tracks/mogis/races with numeric id references."""
        tracks = {t["id"]: ensure_track_id(t.get("name", "")) for t in data.get("tracks", [])}
        mogis_in = data.get("mogis", [])
        races_in = data.get("races", [])
        mogis_out = [{"finalized": m.get("finalized", False), "note": m.get("note", ""), "races": []}
                     for m in mogis_in]
        idx_map = {m_in["id"]: i for i, m_in in enumerate(mogis_in)}
        for r in races_in:
            m_idx = idx_map[r["mogi_id"]]
            mogis_out[m_idx]["races"].append({
                "track": r.get("track_name") or r.get("track") or r.get("track_slug") or r.get("track_id"),
                "position": r.get("position"),
                "index": r.get("index") or r.get("race_number"),
                "points": r.get("points", 0),
            })
        return mogis_out

    def parse_format_B(self, mogi_list):
        """list of mogis, each with nested races (already the target shape)."""
        # Normalize race keys
        out = []
        for m in mogi_list:
            races = m.get("races") or m.get("race_list") or []
            norm = []
            for i, r in enumerate(races, start=1):
                track_name = r.get("track") or r.get("track_name") or (r.get("track_obj", {}) or {}).get("name")
                norm.append({
                    "track": track_name,
                    "position": r.get("position") or r.get("finish") or r.get("place"),
                    "index": r.get("index") or r.get("race_number") or i,
                    "points": r.get("points", 0),
                })
            out.append({"finalized": m.get("finalized", False), "note": m.get("note", ""), "races": norm})
        return out

    def parse_flat_races(self, races):
        """
        Flat list of races (no mogi grouping). We attempt to:
          1) group by an existing key if found (mogi_id / session_id / group),
          2) else chunk sequentially by 12.
        """
        # Try grouping by any obvious grouping key
        group_key = None
        for key in ("mogi_id", "mogi", "session_id", "session", "set", "group"):
            if any(isinstance(r, dict) and key in r for r in races):
                group_key = key
                break

        grouped = defaultdict(list)
        if group_key:
            for r in races:
                grouped[r.get(group_key)].append(r)
            groups = list(grouped.values())
        else:
            # Fallback: auto-chunk by 12 in order
            groups = [races[i:i+12] for i in range(0, len(races), 12)]

        mogis = []
        for g in groups:
            norm = []
            for i, r in enumerate(g, start=1):
                track_name = (r.get("track") or r.get("track_name") or
                              (r.get("track_obj", {}) or {}).get("name"))
                norm.append({
                    "track": track_name,
                    "position": r.get("position") or r.get("finish") or r.get("place"),
                    "index": r.get("index") or r.get("race_number") or i,
                    "points": r.get("points", 0),
                })
            mogis.append({"finalized": len(norm) == 12, "note": "", "races": norm})
        return mogis

    # -------------- Command handler --------------

    def handle(self, *args, **opts):
        username = opts["username"]
        path = opts["json_path"]
        dry_run = opts["dry_run"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found. Create/sign up user first.")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise CommandError(f"Failed reading JSON: {e}")

        # Detect shape
        mogi_blocks = None
        fmt = None

        if isinstance(data, dict) and all(k in data for k in ("tracks", "mogis", "races")):
            fmt = "A"
            mogi_blocks = self.parse_format_A(data)

        elif isinstance(data, dict) and "mogis" in data and isinstance(data["mogis"], list):
            fmt = "B"
            mogi_blocks = self.parse_format_B(data["mogis"])

        elif isinstance(data, list) and data and isinstance(data[0], dict) and "races" in data[0]:
            fmt = "B"
            mogi_blocks = self.parse_format_B(data)

        elif isinstance(data, dict) and "history" in data and isinstance(data["history"], list):
            fmt = "E"
            mogi_blocks = self.parse_flat_races(data["history"])

        elif isinstance(data, list) and data and isinstance(data[0], dict) and "track" in data[0]:
            fmt = "E"
            mogi_blocks = self.parse_flat_races(data)

        else:
            raise CommandError("Unrecognized JSON format. Expected keys: tracks/mogis/races OR list/dict of mogis OR a flat 'history' list of races.")

        # Summarize
        total_mogis = len(mogi_blocks)
        total_races = sum(len(m["races"]) for m in mogi_blocks)
        self.stdout.write(f"Detected format {fmt}. Found {total_mogis} mogis, {total_races} races.")

        if dry_run:
            # Print a tiny preview and exit
            first = mogi_blocks[0] if mogi_blocks else {}
            self.stdout.write(self.style.WARNING(
                f"[DRY-RUN] Example mogi: finalized={first.get('finalized')}, races={len(first.get('races', []))}"
            ))
            return

        # Import
        imported_mogis = 0
        imported_races = 0
        with transaction.atomic():
            for m in mogi_blocks:
                obj = Mogi.objects.create(owner=user, finalized=m.get("finalized", False), note=m.get("note", ""))
                imported_mogis += 1
                for i, r in enumerate(m.get("races", []), start=1):
                    track_name = r.get("track")
                    try:
                        track_id = ensure_track_id(track_name)
                    except Exception:
                        # Skip races without a resolvable track name
                        continue
                    idx = r.get("index") or i
                    pos = int(r.get("position") or r.get("finish") or r.get("place") or 12)
                    pts = int(r.get("points") or 0)
                    Race.objects.create(mogi=obj, track_id=track_id, index=idx, position=pos, points=pts)
                    imported_races += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported {imported_mogis} mogis and {imported_races} races for user '{username}' (format {fmt})."
        ))
