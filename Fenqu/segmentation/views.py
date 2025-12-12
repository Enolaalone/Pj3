from datetime import datetime

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ClusterSegmentationForm, RFMSegmentationForm, RuleSegmentationForm, UploadFileForm
from .models import SegmentationTask, SegmentResult, UserProfile
from .utils import (
    apply_cluster_segmentation,
    apply_rfm_segmentation,
    apply_rule_segmentation,
    generate_sample_data,
    import_csv_data,
)


def dashboard(request: HttpRequest) -> HttpResponse:
    recent_tasks = SegmentationTask.objects.all().order_by("-created_at")[:5]
    total_users = UserProfile.objects.count()
    total_tasks = SegmentationTask.objects.count()
    task_type_counts = (
        SegmentationTask.objects.values("task_type")
        .order_by("task_type")
        .annotate(count=models.Count("id"))
    )
    # 用户统计
    avg_age = UserProfile.objects.aggregate(avg=models.Avg("age"))["avg"] or 0
    total_amount_sum = UserProfile.objects.aggregate(sum=models.Sum("total_amount"))["sum"] or 0
    # 性别分布
    gender_dist = (
        UserProfile.objects.values("gender")
        .annotate(count=models.Count("id"))
        .order_by("-count")
    )
    # 地区分布
    region_dist = (
        UserProfile.objects.values("region")
        .annotate(count=models.Count("id"))
        .order_by("-count")[:5]
    )
    return render(
        request,
        "segmentation/dashboard.html",
        {
            "recent_tasks": recent_tasks,
            "total_users": total_users,
            "total_tasks": total_tasks,
            "task_type_counts": task_type_counts,
            "avg_age": round(avg_age, 1),
            "total_amount_sum": round(total_amount_sum, 2),
            "gender_dist": gender_dist,
            "region_dist": region_dist,
        },
    )


def data_management(request: HttpRequest) -> HttpResponse:
    upload_form = UploadFileForm()
    user_count = UserProfile.objects.count()
    stats = {
        "user_count": user_count,
        "avg_age": UserProfile.objects.aggregate(avg=models.Avg("age"))["avg"] or 0,
        "total_amount": UserProfile.objects.aggregate(sum=models.Sum("total_amount"))["sum"] or 0,
        "avg_purchase_count": UserProfile.objects.aggregate(avg=models.Avg("purchase_count"))["avg"] or 0,
    }
    preview = UserProfile.objects.all()[:20]
    # 数据分布统计
    gender_dist = (
        UserProfile.objects.values("gender")
        .annotate(count=models.Count("id"))
        .order_by("-count")
    )
    region_dist = (
        UserProfile.objects.values("region")
        .annotate(count=models.Count("id"))
        .order_by("-count")
    )
    channel_dist = (
        UserProfile.objects.values("last_channel")
        .annotate(count=models.Count("id"))
        .order_by("-count")[:5]
    )

    if request.method == "POST":
        if "upload" in request.POST:
            upload_form = UploadFileForm(request.POST, request.FILES)
            if upload_form.is_valid():
                file_obj = upload_form.cleaned_data["file"]
                saved_path = default_storage.save(f"uploads/{file_obj.name}", file_obj)
                with default_storage.open(saved_path, "r") as f:
                    try:
                        res = import_csv_data(f)
                        messages.success(request, f"导入成功，新增 {res['inserted']} 条用户数据")
                    except Exception as exc:  # pylint: disable=broad-except
                        messages.error(request, f"导入失败: {exc}")
                return redirect(reverse("segmentation:data_management"))
        if "sample" in request.POST:
            buffer = generate_sample_data()
            res = import_csv_data(buffer)
            messages.success(request, f"示例数据已导入，新增 {res['inserted']} 条用户数据")
            return redirect(reverse("segmentation:data_management"))

    return render(
        request,
        "segmentation/data_management.html",
        {
            "upload_form": upload_form,
            "stats": stats,
            "preview": preview,
            "gender_dist": gender_dist,
            "region_dist": region_dist,
            "channel_dist": channel_dist,
        },
    )


def _create_task(task_name: str, task_type: str, config: dict) -> SegmentationTask:
    with transaction.atomic():
        task = SegmentationTask.objects.create(task_name=task_name, task_type=task_type, config=config)
    return task


def rule_segmentation(request: HttpRequest) -> HttpResponse:
    form = RuleSegmentationForm(request.POST or None)
    preview_count = None
    if request.method == "POST" and form.is_valid():
        config = form.cleaned_data
        task = _create_task(
            task_name=f"规则分群 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            task_type="rule",
            config=config,
        )
        matched = apply_rule_segmentation(task, config)
        messages.success(request, f"规则分群完成，匹配用户 {matched} 个")
        return redirect(reverse("segmentation:result_detail", args=[task.id]))

    # preview count if possible
    if form.is_valid():
        config = form.cleaned_data
        qs = UserProfile.objects.all()
        if config.get("age_min") is not None:
            qs = qs.filter(age__gte=config["age_min"])
        if config.get("age_max") is not None:
            qs = qs.filter(age__lte=config["age_max"])
        if config.get("gender"):
            qs = qs.filter(gender=config["gender"])
        if config.get("region"):
            qs = qs.filter(region__icontains=config["region"])
        if config.get("purchase_count_min") is not None:
            qs = qs.filter(purchase_count__gte=config["purchase_count_min"])
        if config.get("purchase_count_max") is not None:
            qs = qs.filter(purchase_count__lte=config["purchase_count_max"])
        if config.get("total_amount_min") is not None:
            qs = qs.filter(total_amount__gte=config["total_amount_min"])
        if config.get("total_amount_max") is not None:
            qs = qs.filter(total_amount__lte=config["total_amount_max"])
        if config.get("last_channel"):
            qs = qs.filter(last_channel__icontains=config["last_channel"])
        preview_count = qs.count()

    return render(request, "segmentation/rule_segmentation.html", {"form": form, "preview_count": preview_count})


def rfm_segmentation(request: HttpRequest) -> HttpResponse:
    form = RFMSegmentationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        config = form.cleaned_data
        task = _create_task(
            task_name=f"RFM分群 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            task_type="rfm",
            config=config,
        )
        matched = apply_rfm_segmentation(task, config)
        messages.success(request, f"RFM 分群完成，处理用户 {matched} 个")
        return redirect(reverse("segmentation:result_detail", args=[task.id]))

    return render(request, "segmentation/rfm_segmentation.html", {"form": form})


def cluster_segmentation(request: HttpRequest) -> HttpResponse:
    form = ClusterSegmentationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        config = form.cleaned_data
        task = _create_task(
            task_name=f"聚类分群 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            task_type="cluster",
            config=config,
        )
        matched = apply_cluster_segmentation(task, config)
        messages.success(request, f"聚类分群完成，处理用户 {matched} 个")
        return redirect(reverse("segmentation:result_detail", args=[task.id]))

    return render(request, "segmentation/cluster_segmentation.html", {"form": form})


def results_list(request: HttpRequest) -> HttpResponse:
    tasks = SegmentationTask.objects.all()
    return render(request, "segmentation/results_list.html", {"tasks": tasks})


def result_detail(request: HttpRequest, task_id: int) -> HttpResponse:
    task = get_object_or_404(SegmentationTask, id=task_id)
    results = SegmentResult.objects.filter(task=task)[:500]
    total_results = SegmentResult.objects.filter(task=task).count()
    # 分群分布统计
    segment_dist = (
        SegmentResult.objects.filter(task=task)
        .values("segment_value")
        .annotate(count=models.Count("id"))
        .order_by("-count")
    )
    return render(
        request,
        "segmentation/result_detail.html",
        {
            "task": task,
            "results": results,
            "total_results": total_results,
            "segment_dist": segment_dist,
        },
    )
