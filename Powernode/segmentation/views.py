from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import UploadForm
from .models import UserClusterProfile
from .services import process_upload


def upload_view(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return HttpResponseBadRequest("表单无效")
        file = form.cleaned_data["file"]
        cluster_count = form.cleaned_data.get("cluster_count") or 4
        try:
            summaries, samples = process_upload(file, cluster_count=cluster_count)
        except Exception as exc:
            return render(
                request,
                "segmentation/upload.html",
                {"form": form, "error": str(exc)},
                status=400,
            )
        request.session["last_summaries"] = summaries
        request.session["last_samples"] = samples
        return redirect(reverse("segmentation:result"))
    else:
        form = UploadForm()
    return render(request, "segmentation/upload.html", {"form": form})


def result_view(request):
    summaries = request.session.get("last_summaries", [])
    samples = request.session.get("last_samples", [])
    return render(
        request,
        "segmentation/result.html",
        {"summaries": summaries, "samples": samples},
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

