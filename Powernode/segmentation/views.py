from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.core.paginator import Paginator
from django.utils.dateparse import parse_datetime

from .forms import UploadForm
from .models import UserClusterProfile, OrderRecord
from .services import process_upload


def upload_view(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return HttpResponseBadRequest("表单无效")
        file = form.cleaned_data["file"]
        cluster_count = form.cleaned_data.get("cluster_count") or 4
        auto_k = form.cleaned_data.get("auto_k") or False
        auto_k_multi = form.cleaned_data.get("auto_k_multi") or True
        k_min = form.cleaned_data.get("k_min") or 2
        k_max = form.cleaned_data.get("k_max") or 8
        try:
            summaries, samples, metrics, chart_data = process_upload(
                file,
                cluster_count=cluster_count,
                auto_k=auto_k,
                auto_k_multi=auto_k_multi,
                k_min=k_min,
                k_max=k_max,
            )
        except Exception as exc:
            return render(
                request,
                "segmentation/upload.html",
                {"form": form, "error": str(exc)},
                status=400,
            )
        request.session["last_summaries"] = summaries
        request.session["last_samples"] = samples
        request.session["last_metrics"] = metrics
        request.session["last_chart_data"] = chart_data
        return redirect(reverse("segmentation:overview"))
    else:
        form = UploadForm()
    return render(request, "segmentation/upload.html", {"form": form, "nav_active": "upload"})


def overview_view(request):
    summaries = request.session.get("last_summaries", [])
    metrics = request.session.get("last_metrics", {})
    return render(
        request,
        "segmentation/overview.html",
        {"summaries": summaries, "metrics": metrics, "nav_active": "overview"},
    )


def charts_view(request):
    metrics = request.session.get("last_metrics", {})
    chart_data = request.session.get("last_chart_data", {})
    cluster_filter = request.GET.get("cluster")
    category_filter = request.GET.get("category")
    channel_filter = request.GET.get("channel")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    # 基于过滤条件重新计算图表数据
    orders = OrderRecord.objects.all()
    if category_filter:
        orders = orders.filter(category=category_filter)
    if channel_filter:
        orders = orders.filter(channel=channel_filter)
    if date_from:
        dt = parse_datetime(date_from)
        if dt:
            orders = orders.filter(order_time__gte=dt)
    if date_to:
        dt = parse_datetime(date_to)
        if dt:
            orders = orders.filter(order_time__lte=dt)

    profiles = {p.user_id: p.cluster_id for p in UserClusterProfile.objects.all()}
    records = []
    for o in orders:
        cid = profiles.get(o.user_id)
        if cid is None:
            continue
        records.append(
            {
                "user_id": o.user_id,
                "cluster_id": cid,
                "amount": float(o.amount),
                "order_id": o.order_id,
                "order_time": o.order_time,
                "category": o.category,
                "channel": o.channel,
            }
        )
    import pandas as pd

    if records:
        df = pd.DataFrame(records)
        if cluster_filter not in (None, "", "all"):
            try:
                cf = int(cluster_filter)
                df = df[df["cluster_id"] == cf]
            except ValueError:
                pass
        # 用户级聚合
        user_agg = df.groupby(["user_id", "cluster_id"]).agg(
            total_amount=("amount", "sum"),
            order_count=("order_id", "count"),
            avg_amount=("amount", "mean"),
        )
        user_agg["promo_ratio"] = 0.0
        user_agg["refund_ratio"] = 0.0
        user_agg["recency_days"] = 0.0
        user_agg = user_agg.reset_index()
        cluster_means = (
            user_agg.groupby("cluster_id")[
                ["total_amount", "order_count", "avg_amount", "promo_ratio", "refund_ratio", "recency_days"]
            ]
            .mean()
            .reset_index()
            .replace({pd.NA: 0, float("nan"): 0})
        )
        cluster_means_records = [
            {k: (float(v) if hasattr(v, "__float__") else v) for k, v in row.items()}
            for row in cluster_means.to_dict(orient="records")
        ]
        chart_data = {"cluster_means": cluster_means_records}
    else:
        chart_data = {"cluster_means": []}

    return render(
        request,
        "segmentation/charts.html",
        {
            "metrics": metrics,
            "chart_data": chart_data,
            "nav_active": "charts",
            "filters": {
                "cluster": cluster_filter or "",
                "category": category_filter or "",
                "channel": channel_filter or "",
                "date_from": date_from or "",
                "date_to": date_to or "",
            },
        },
    )


def samples_view(request):
    samples = request.session.get("last_samples", [])
    return render(
        request,
        "segmentation/samples.html",
        {"samples": samples, "nav_active": "samples"},
    )


def orders_view(request):
    orders_qs = OrderRecord.objects.all().order_by("-order_time")
    paginator = Paginator(orders_qs, 20)
    page_number = request.GET.get("page", 1)
    orders_page = paginator.get_page(page_number)
    return render(
        request,
        "segmentation/orders.html",
        {"orders_page": orders_page, "nav_active": "orders"},
    )


def download_clusters(request):
    profiles = UserClusterProfile.objects.all()
    headers = [
        "user_id",
        "cluster_id",
        "total_amount",
        "order_count",
        "avg_amount",
        "promo_ratio",
        "refund_ratio",
        "last_order_time",
        "top_category",
        "top_channel",
        "top_device",
    ]
    lines = [",".join(headers)]
    for p in profiles:
        lines.append(
            ",".join(
                [
                    p.user_id,
                    str(p.cluster_id),
                    str(p.total_amount),
                    str(p.order_count),
                    str(p.avg_amount),
                    str(p.promo_ratio),
                    str(p.refund_ratio),
                    p.last_order_time.isoformat(),
                    p.top_category,
                    p.top_channel,
                    p.top_device,
                ]
            )
        )
    content = "\n".join(lines)
    resp = HttpResponse(content, content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="clusters.csv"'
    return resp

