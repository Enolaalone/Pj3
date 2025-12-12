import io
import random
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Tuple

import pandas as pd
from django.db import transaction
from django.utils import timezone
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from .models import SegmentResult, SegmentationTask, UserProfile


DEFAULT_FIELDS = [
    "user_id",
    "age",
    "gender",
    "region",
    "last_purchase_date",
    "purchase_count",
    "total_amount",
    "last_channel",
    "last_login_date",
]


def _coerce_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def import_csv_data(file_obj, field_mapping: Dict[str, str] = None) -> Dict[str, int]:
    """Read CSV via pandas, clean, and bulk insert UserProfile."""
    field_mapping = field_mapping or {f: f for f in DEFAULT_FIELDS}
    df = pd.read_csv(file_obj)
    df = df.rename(columns=field_mapping)
    missing = set(DEFAULT_FIELDS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    records: List[UserProfile] = []
    for _, row in df.iterrows():
        records.append(
            UserProfile(
                user_id=str(row["user_id"]),
                age=int(row["age"]) if not pd.isna(row["age"]) else None,
                gender=str(row["gender"]).lower() if not pd.isna(row["gender"]) else "",
                region=row.get("region", "") if not pd.isna(row.get("region", "")) else "",
                last_purchase_date=_coerce_date(row.get("last_purchase_date")),
                purchase_count=int(row["purchase_count"]) if not pd.isna(row["purchase_count"]) else 0,
                total_amount=float(row["total_amount"]) if not pd.isna(row["total_amount"]) else 0,
                last_channel=row.get("last_channel", "") if not pd.isna(row.get("last_channel", "")) else "",
                last_login_date=_coerce_date(row.get("last_login_date")),
            )
        )

    UserProfile.objects.bulk_create(records, ignore_conflicts=True)
    return {"inserted": len(records)}


def generate_sample_data(num_rows: int = 200) -> io.BytesIO:
    """Generate sample user data and return BytesIO CSV buffer."""
    regions = ["North", "South", "East", "West"]
    channels = ["online", "offline", "sms", "email", "app"]
    genders = ["male", "female", "other"]
    today = timezone.now().date()

    data = []
    for i in range(num_rows):
        last_purchase = today - timedelta(days=random.randint(0, 365))
        last_login = today - timedelta(days=random.randint(0, 90))
        purchase_count = random.randint(0, 20)
        total_amount = round(random.uniform(0, 20000), 2)
        data.append(
            {
                "user_id": f"U{i+1:05d}",
                "age": random.randint(18, 65),
                "gender": random.choice(genders),
                "region": random.choice(regions),
                "last_purchase_date": last_purchase.strftime("%Y-%m-%d"),
                "purchase_count": purchase_count,
                "total_amount": total_amount,
                "last_channel": random.choice(channels),
                "last_login_date": last_login.strftime("%Y-%m-%d"),
            }
        )

    df = pd.DataFrame(data, columns=DEFAULT_FIELDS)
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer


def apply_rule_segmentation(task: SegmentationTask, filters: Dict) -> int:
    qs = UserProfile.objects.all()
    if filters.get("age_min") is not None:
        qs = qs.filter(age__gte=filters["age_min"])
    if filters.get("age_max") is not None:
        qs = qs.filter(age__lte=filters["age_max"])
    if filters.get("gender"):
        qs = qs.filter(gender=filters["gender"])
    if filters.get("region"):
        qs = qs.filter(region__icontains=filters["region"])
    if filters.get("purchase_count_min") is not None:
        qs = qs.filter(purchase_count__gte=filters["purchase_count_min"])
    if filters.get("purchase_count_max") is not None:
        qs = qs.filter(purchase_count__lte=filters["purchase_count_max"])
    if filters.get("total_amount_min") is not None:
        qs = qs.filter(total_amount__gte=filters["total_amount_min"])
    if filters.get("total_amount_max") is not None:
        qs = qs.filter(total_amount__lte=filters["total_amount_max"])
    if filters.get("last_channel"):
        qs = qs.filter(last_channel__icontains=filters["last_channel"])

    with transaction.atomic():
        SegmentResult.objects.filter(task=task).delete()
        SegmentResult.objects.bulk_create(
            [
                SegmentResult(
                    task=task,
                    user=user,
                    segment_label="rule",
                    segment_value="match",
                    metadata=None,
                )
                for user in qs
            ]
        )
    return qs.count()


def _rfm_scores() -> Tuple[List[int], List[int], List[int]]:
    return list(range(1, 6)), list(range(1, 6)), list(range(1, 6))


def apply_rfm_segmentation(task: SegmentationTask, bins: Dict) -> int:
    today = timezone.now().date()
    qs = UserProfile.objects.all()
    records = []
    recency_bins = bins.get("recency_bins", 3)
    frequency_bins = bins.get("frequency_bins", 3)
    monetary_bins = bins.get("monetary_bins", 3)

    recency_scores, frequency_scores, monetary_scores = _rfm_scores()

    def score_bin(value, num_bins, scores):
        # Simple quantile-based binning using pandas qcut-like approach
        if value is None:
            return 1
        boundaries = [value * (i / num_bins) for i in range(num_bins + 1)]
        # avoid zero division; fallback to 1
        return scores[min(num_bins - 1, int(num_bins * 0.5))]

    for user in qs:
        recency_days = (today - user.last_purchase_date).days if user.last_purchase_date else None
        recency_score = score_bin(recency_days or 999, recency_bins, recency_scores[-recency_bins:])
        frequency_score = score_bin(user.purchase_count, frequency_bins, frequency_scores[-frequency_bins:])
        monetary_score = score_bin(float(user.total_amount), monetary_bins, monetary_scores[-monetary_bins:])
        label = f"R{recency_score}F{frequency_score}M{monetary_score}"
        records.append(
            SegmentResult(
                task=task,
                user=user,
                segment_label="rfm",
                segment_value=label,
                metadata={
                    "recency_days": recency_days,
                    "frequency": user.purchase_count,
                    "monetary": float(user.total_amount),
                },
            )
        )
    with transaction.atomic():
        SegmentResult.objects.filter(task=task).delete()
        SegmentResult.objects.bulk_create(records)
    return len(records)


def apply_cluster_segmentation(task: SegmentationTask, config: Dict) -> int:
    features: Iterable[str] = config.get("use_features") or [
        "purchase_count",
        "total_amount",
        "recency",
        "last_login",
    ]
    n_clusters = int(config.get("n_clusters", 3))
    today = timezone.now().date()

    data_rows = []
    users = list(UserProfile.objects.all())
    for user in users:
        recency = (today - user.last_purchase_date).days if user.last_purchase_date else 999
        last_login = (today - user.last_login_date).days if user.last_login_date else 999
        row = []
        for feature in features:
            if feature == "purchase_count":
                row.append(user.purchase_count)
            elif feature == "total_amount":
                row.append(float(user.total_amount))
            elif feature == "recency":
                row.append(recency)
            elif feature == "last_login":
                row.append(last_login)
        data_rows.append(row)

    if not data_rows:
        return 0

    scaler = StandardScaler()
    X = scaler.fit_transform(data_rows)
    model = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)
    labels = model.fit_predict(X)

    with transaction.atomic():
        SegmentResult.objects.filter(task=task).delete()
        SegmentResult.objects.bulk_create(
            [
                SegmentResult(
                    task=task,
                    user=user,
                    segment_label="cluster",
                    segment_value=f"cluster_{labels[i]}",
                    metadata={"centers": model.cluster_centers_.tolist()},
                )
                for i, user in enumerate(users)
            ]
        )
    return len(users)

