from django.contrib import admin

from .models import OrderRecord, UserClusterProfile


@admin.register(OrderRecord)
class OrderRecordAdmin(admin.ModelAdmin):
    list_display = ("order_id", "user_id", "order_time", "amount", "category", "channel")
    search_fields = ("order_id", "user_id", "category", "channel")
    list_filter = ("channel", "device", "refund_flag", "is_promo")


@admin.register(UserClusterProfile)
class UserClusterProfileAdmin(admin.ModelAdmin):
    list_display = ("user_id", "cluster_id", "total_amount", "order_count", "avg_amount", "top_category")
    search_fields = ("user_id", "top_category", "top_channel")
    list_filter = ("cluster_id",)

