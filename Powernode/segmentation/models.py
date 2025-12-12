from django.db import models


class OrderRecord(models.Model):
    user_id = models.CharField(max_length=64, db_index=True)
    order_id = models.CharField(max_length=128, unique=True)
    order_time = models.DateTimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=128, blank=True, default="")
    is_promo = models.BooleanField(default=False)
    refund_flag = models.BooleanField(default=False)
    device = models.CharField(max_length=64, blank=True, default="")
    channel = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-order_time"]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.order_id}"


class UserClusterProfile(models.Model):
    user_id = models.CharField(max_length=64, db_index=True)
    cluster_id = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    order_count = models.PositiveIntegerField()
    avg_amount = models.DecimalField(max_digits=12, decimal_places=2)
    promo_ratio = models.DecimalField(max_digits=5, decimal_places=2)
    refund_ratio = models.DecimalField(max_digits=5, decimal_places=2)
    last_order_time = models.DateTimeField()
    top_category = models.CharField(max_length=128, blank=True, default="")
    top_channel = models.CharField(max_length=64, blank=True, default="")
    top_device = models.CharField(max_length=64, blank=True, default="")
    run_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["cluster_id"]), models.Index(fields=["run_at"])]
        ordering = ["cluster_id", "-total_amount"]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.cluster_id}"


