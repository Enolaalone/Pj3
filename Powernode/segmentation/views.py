from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.core.paginator import Paginator

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
        k_min = form.cleaned_data.get("k_min") or 2
        k_max = form.cleaned_data.get("k_max") or 8
        try:
            summaries, samples, metrics, chart_data = process_upload(
                file,
                cluster_count=cluster_count,
                auto_k=auto_k,
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
    return render(
        request,
        "segmentation/charts.html",
        {"metrics": metrics, "chart_data": chart_data, "nav_active": "charts"},
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

