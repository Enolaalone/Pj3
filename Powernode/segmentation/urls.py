from django.urls import path

from . import views

app_name = "segmentation"

urlpatterns = [
    path("", views.upload_view, name="upload"),
    path("result/", views.result_view, name="result"),
    path("download/", views.download_clusters, name="download"),
]

