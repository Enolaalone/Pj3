import io
from datetime import datetime

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import OrderRecord, UserClusterProfile
from .services import load_csv_to_df, process_upload


def sample_csv_bytes() -> bytes:
    return b"""user_id,order_id,order_time,amount,category,is_promo,refund_flag,device,channel
U001,ORD1001,2024-07-01 10:23:00,259.00,Home,0,0,Mobile,App
U001,ORD1055,2024-07-15 20:11:00,1299.00,Electronics,1,0,Mobile,App
U002,ORD1002,2024-07-02 08:55:00,59.00,Grocery,0,0,Web,PC
"""


class ServiceTests(TestCase):
    def test_load_csv_to_df_success(self):
        df = load_csv_to_df(io.BytesIO(sample_csv_bytes()))
        self.assertEqual(set(df.columns), set([  # exact required columns
            "user_id",
            "order_id",
            "order_time",
            "amount",
            "category",
            "is_promo",
            "refund_flag",
            "device",
            "channel",
        ]))
        self.assertEqual(len(df), 3)
        self.assertTrue(pd.api.types.is_datetime64tz_dtype(df["order_time"]))

    def test_process_upload_pipeline(self):
        summaries, samples, metrics, chart_data = process_upload(
            io.BytesIO(sample_csv_bytes()), cluster_count=2
        )
        self.assertGreaterEqual(len(summaries), 1)
        self.assertGreaterEqual(len(samples), 2)
        self.assertEqual(OrderRecord.objects.count(), 3)
        self.assertEqual(UserClusterProfile.objects.count(), 2)
        # cluster ids should be consecutive starting at 0
        cluster_ids = sorted(UserClusterProfile.objects.values_list("cluster_id", flat=True))
        self.assertEqual(cluster_ids, [0, 1])
        self.assertEqual(metrics["k_used"], 2)
        self.assertIn("cluster_means", chart_data)

    def test_process_upload_auto_k(self):
        summaries, samples, metrics, chart_data = process_upload(
            io.BytesIO(sample_csv_bytes()), auto_k=True, k_min=2, k_max=3
        )
        self.assertTrue(metrics["k_auto"])
        self.assertIn(metrics["k_used"], [2, 3])
        self.assertGreaterEqual(len(metrics.get("scores", [])), 1)


class ViewTests(TestCase):
    def test_upload_and_result_flow(self):
        client = Client()
        upload_file = SimpleUploadedFile("data.csv", sample_csv_bytes(), content_type="text/csv")
        resp = client.post(reverse("segmentation:upload"), {"file": upload_file, "cluster_count": 2})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("segmentation:result"))

        resp_result = client.get(reverse("segmentation:result"))
        self.assertContains(resp_result, "分群概览")
        self.assertContains(resp_result, "Cluster")

    def test_download_clusters(self):
        # prepare data
        process_upload(io.BytesIO(sample_csv_bytes()), cluster_count=2)
        client = Client()
        resp = client.get(reverse("segmentation:download"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        content = resp.content.decode("utf-8")
        self.assertIn("user_id,cluster_id", content.splitlines()[0])

