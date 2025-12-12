from django.db import models
from django.contrib.auth import get_user_model


User = get_user_model()


class UserProfile(models.Model):
    GENDER_CHOICES = (
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    )

    user_id = models.CharField(max_length=64, unique=True)
    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    region = models.CharField(max_length=128, blank=True)
    last_purchase_date = models.DateField(null=True, blank=True)
    purchase_count = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_channel = models.CharField(max_length=128, blank=True)
    last_login_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.user_id


class SegmentationTask(models.Model):
    TASK_TYPE_CHOICES = (
        ("rule", "Rule"),
        ("rfm", "RFM"),
        ("cluster", "Cluster"),
    )

    task_name = models.CharField(max_length=128)
    task_type = models.CharField(max_length=16, choices=TASK_TYPE_CHOICES)
    config = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.task_name} ({self.task_type})"


class SegmentResult(models.Model):
    task = models.ForeignKey(SegmentationTask, on_delete=models.CASCADE, related_name="results")
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="segments")
    segment_label = models.CharField(max_length=64)
    segment_value = models.CharField(max_length=64)
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["segment_label"]),
            models.Index(fields=["segment_value"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.user_id}:{self.segment_value}"
from django.db import models

# Create your models here.
