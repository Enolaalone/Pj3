from django.urls import path

from . import views


app_name = "segmentation"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("data/", views.data_management, name="data_management"),
    path("segment/rule/", views.rule_segmentation, name="rule_segmentation"),
    path("segment/rfm/", views.rfm_segmentation, name="rfm_segmentation"),
    path("segment/cluster/", views.cluster_segmentation, name="cluster_segmentation"),
    path("results/", views.results_list, name="results_list"),
    path("results/<int:task_id>/", views.result_detail, name="result_detail"),
]

