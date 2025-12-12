from django.urls import path

from . import views

app_name = "segmentation"

urlpatterns = [
    path("", views.upload_view, name="upload"),
    path("overview/", views.overview_view, name="overview"),
    path("charts/", views.charts_view, name="charts"),
    path("samples/", views.samples_view, name="samples"),
    path("orders/", views.orders_view, name="orders"),
    path("download/", views.download_clusters, name="download"),
]

