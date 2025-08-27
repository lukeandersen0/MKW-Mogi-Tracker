
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.db.models import Count, Avg, Sum, Q, Min, Max
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from .forms import SignUpForm
from .models import Track, Mogi, Race
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login
from django.shortcuts import render, redirect

def signup(request):
    if request.user.is_authenticated:
        return redirect("mogi:dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            user.save()
            login(request, user)
            return redirect("mogi:dashboard")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})

def _current_mogi(user):
    m = Mogi.objects.filter(owner=user, finalized=False).order_by("created_at").first()
    return m or Mogi.objects.create(owner=user)

def _mogi_numbering_map(user):
    ids_oldest_first = list(
        Mogi.objects.filter(owner=user, finalized=True)
        .order_by("created_at")
        .values_list("id", flat=True)
    )
    return {mid: i + 1 for i, mid in enumerate(ids_oldest_first)}

def _sorted_mogis(user, sort: str):
    qs = Mogi.objects.filter(owner=user, finalized=True)
    return qs.order_by("created_at") if sort == "oldest" else qs.order_by("-created_at")

# ---------- Pages ----------

@login_required
def dashboard(request):
    mogi = _current_mogi(request.user)
    completed = _sorted_mogis(request.user, "newest")
    numbering_map = _mogi_numbering_map(request.user)

    track_perf = (
        Track.objects
        .annotate(
            times=Count("races"),
            avg_finish=Avg("races__position"),
        )
        .filter(times__gt=0)
        .order_by("avg_finish", "name")[:10]  # Top 10, best avg first
    )

    tracks = Track.objects.all().order_by("name")

    return render(request, "mogi/dashboard.html", {
        "mogi": mogi,
        "completed": completed,
        "numbering_map": numbering_map,
        "track_perf": track_perf,
        "tracks": tracks,
    })

@login_required
def mogi_list(request):
    mogis = _sorted_mogis(request.user, "newest")
    numbering_map = _mogi_numbering_map(request.user)
    return render(request, "mogi/mogi_list.html", {
        "mogis": mogis,
        "numbering_map": numbering_map,
        "default_sort": "newest",
    })

@login_required
def mogi_detail(request, mogi_id: int):
    mogi = get_object_or_404(Mogi, id=mogi_id, owner=request.user)
    races = mogi.races.select_related("track").order_by("index")
    return render(request, "mogi/mogi_detail.html", {"mogi": mogi, "races": races})

@login_required
def track_list(request):
    tracks = Track.objects.annotate(rc=Count("races")).order_by("-rc", "name")
    return render(request, "mogi/track_list.html", {"tracks": tracks})

@login_required
def track_detail(request, slug):
    track = get_object_or_404(Track, slug=slug)
    races = Race.objects.filter(track=track, mogi__owner=request.user).select_related("mogi").order_by("-mogi__played_at")

    stats = races.aggregate(
        times=Count("id"),
        avg_finish=Avg("position"),
        best=Min("position"),
        worst=Max("position"),
        total_points=Sum("points"),
        avg_points=Avg("points"),
    )

    # distribution: count by position 1–12
    distribution = races.values("position").annotate(count=Count("id")).order_by("position")
    dist_map = {d["position"]: d["count"] for d in distribution}
    # fill missing positions with 0
    finish_dist = [(i, dist_map.get(i, 0)) for i in range(1, 13)]

    return render(request, "mogi/track_detail.html", {
        "track": track,
        "races": races,
        "stats": stats,
        "finish_dist": finish_dist,
    })

@login_required
def race_history(request):
    races = Race.objects.select_related("mogi", "track").filter(mogi__owner=request.user).order_by("-mogi__created_at", "-index")
    return render(request, "mogi/history.html", {"races": races})

@login_required
def all_time_stats(request):
    total_mogis = Mogi.objects.filter(owner=request.user, finalized=True).count()
    total_races = Race.objects.filter(mogi__owner=request.user).count()

    best_tracks = (Track.objects
                   .annotate(
                       total_pts=Sum("races__points", filter=Q(races__mogi__owner=request.user)),
                       avg_finish=Avg("races__position", filter=Q(races__mogi__owner=request.user)),
                       times=Count("races", filter=Q(races__mogi__owner=request.user)),
                   )
                   .filter(times__gt=0)
                   .order_by("-total_pts")[:20])

    worst_finishes = (Race.objects.filter(mogi__owner=request.user)
                      .values("track__name")
                      .annotate(avg=Avg("position"), n=Count("id"))
                      .order_by("-avg")[:10])

    return render(request, "mogi/stats.html", {
        "total_mogis": total_mogis,
        "total_races": total_races,
        "best_tracks": best_tracks,
        "worst_finishes": worst_finishes,
    })

# ---------- Live fragments (sort toggle) ----------

@login_required
def mogi_cards_fragment(request):
    sort = request.GET.get("sort", "newest")
    numbering_map = _mogi_numbering_map(request.user)
    mogis = _sorted_mogis(request.user, sort)
    html = render_to_string("mogi/includes/mogi_cards.html", {
        "mogis": mogis,
        "numbering_map": numbering_map,
    }, request=request)
    return HttpResponse(html)

@login_required
def dashboard_cards_fragment(request):
    sort = request.GET.get("sort", "newest")
    numbering_map = _mogi_numbering_map(request.user)
    mogis = _sorted_mogis(request.user, sort)
    html = render_to_string("mogi/includes/dashboard_cards.html", {
        "completed": mogis,
        "numbering_map": numbering_map,
    }, request=request)
    return HttpResponse(html)

def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("mogi:dashboard")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})