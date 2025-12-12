from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from django.db import transaction
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from .models import OrderRecord, UserClusterProfile

REQUIRED_COLUMNS = [
    "user_id",
    "order_id",
    "order_time",
    "amount",
    "category",
    "is_promo",
    "refund_flag",
    "device",
    "channel",
]


def load_csv_to_df(uploaded_file) -> pd.DataFrame:
    """Read CSV into DataFrame with basic validation and type coercion."""
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as exc:  # pragma: no cover - pandas parse error path
        raise ValueError(f"CSV 解析失败: {exc}") from exc

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必要列: {', '.join(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    # 类型与清洗
    df["order_time"] = pd.to_datetime(df["order_time"], errors="coerce", utc=True)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["is_promo"] = df["is_promo"].astype(int)
    df["refund_flag"] = df["refund_flag"].astype(int)

    df = df.dropna(subset=["user_id", "order_id", "order_time", "amount"])
    if df.empty:
        raise ValueError("有效记录为空，请检查数据。")
    return df


def persist_orders(df: pd.DataFrame) -> None:
    """Persist order records; ignore duplicates by order_id."""
    records = [
        OrderRecord(
            user_id=row.user_id,
            order_id=row.order_id,
            order_time=row.order_time.to_pydatetime(),
            amount=Decimal(str(row.amount)),
            category=row.category or "",
            is_promo=bool(row.is_promo),
            refund_flag=bool(row.refund_flag),
            device=row.device or "",
            channel=row.channel or "",
        )
        for row in df.itertuples(index=False)
    ]
    OrderRecord.objects.bulk_create(records, ignore_conflicts=True)


def build_user_features(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate user-level features for clustering."""
    now = datetime.now(timezone.utc)
    agg = df.groupby("user_id").agg(
        total_amount=("amount", "sum"),
        order_count=("order_id", "count"),
        avg_amount=("amount", "mean"),
        promo_ratio=("is_promo", "mean"),
        refund_ratio=("refund_flag", "mean"),
        last_order_time=("order_time", "max"),
    )

    # 最近一次订单距今
    agg["recency_days"] = (now - agg["last_order_time"]).dt.total_seconds() / 86400.0

    # Top categorical preferences
    def top_value(series: Iterable[str]) -> str:
        cnt = Counter(x for x in series if isinstance(x, str))
        return cnt.most_common(1)[0][0] if cnt else ""

    top_cat = df.groupby("user_id")["category"].apply(top_value)
    top_channel = df.groupby("user_id")["channel"].apply(top_value)
    top_device = df.groupby("user_id")["device"].apply(top_value)

    agg["top_category"] = top_cat
    agg["top_channel"] = top_channel
    agg["top_device"] = top_device
    agg = agg.reset_index()
    return agg


def run_kmeans(user_features: pd.DataFrame, n_clusters: int = 4) -> Tuple[pd.DataFrame, Dict]:
    """Standardize numeric features and run KMeans."""
    numeric_cols = [
        "total_amount",
        "order_count",
        "avg_amount",
        "promo_ratio",
        "refund_ratio",
        "recency_days",
    ]
    data = user_features.copy()
    scaler = StandardScaler()
    data_scaled = scaler.fit_transform(data[numeric_cols])
    kmeans = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)
    labels = kmeans.fit_predict(data_scaled)
    data["cluster_id"] = labels
    return data, {"centers": kmeans.cluster_centers_, "inertia": kmeans.inertia_}


def choose_k_auto(
    user_features: pd.DataFrame,
    k_min: int = 2,
    k_max: int = 8,
    multi_metric: bool = True,
) -> Tuple[int, List[Dict], str]:
    """Auto-select K with multiple metrics; priority silhouette > CH > DBI > inertia."""
    n_samples = len(user_features)
    if n_samples < 2:
        raise ValueError("样本太少，无法分群（至少2个用户）。")
    # 自适应范围：上限不超过样本数-1，且不大于10
    effective_k_min = max(2, k_min or 2)
    effective_k_max = max(effective_k_min, min(k_max or 8, n_samples - 1, 10))
    numeric_cols = [
        "total_amount",
        "order_count",
        "avg_amount",
        "promo_ratio",
        "refund_ratio",
        "recency_days",
    ]
    scaler = StandardScaler()
    data_scaled = scaler.fit_transform(user_features[numeric_cols])
    scores: List[Dict] = []
    for k in range(effective_k_min, effective_k_max + 1):
        if k < 2:
            continue
        model = KMeans(n_clusters=k, n_init="auto", random_state=42)
        labels = model.fit_predict(data_scaled)
        inertia = float(model.inertia_)
        sil = None
        ch = None
        dbi = None
        try:
            sil = float(silhouette_score(data_scaled, labels)) if len(set(labels)) > 1 else None
        except Exception:
            sil = None
        if multi_metric:
            try:
                ch = float(calinski_harabasz_score(data_scaled, labels))
            except Exception:
                ch = None
            try:
                dbi = float(davies_bouldin_score(data_scaled, labels))
            except Exception:
                dbi = None
        scores.append({"k": k, "inertia": inertia, "silhouette": sil, "ch": ch, "dbi": dbi})
    # 选择规则：silhouette 最大；否则 CH 最大；否则 DBI 最小；否则 inertia 最小
    def pick_best():
        valid_sil = [s for s in scores if s["silhouette"] is not None]
        if valid_sil:
            return max(valid_sil, key=lambda x: x["silhouette"]), "silhouette"
        if multi_metric:
            valid_ch = [s for s in scores if s["ch"] is not None]
            if valid_ch:
                return max(valid_ch, key=lambda x: x["ch"]), "calinski_harabasz"
            valid_dbi = [s for s in scores if s["dbi"] is not None]
            if valid_dbi:
                return min(valid_dbi, key=lambda x: x["dbi"]), "davies_bouldin"
        return min(scores, key=lambda x: x["inertia"]), "inertia"

    best, method = pick_best()
    return int(best["k"]), scores, method


def make_cluster_tags(clustered: pd.DataFrame) -> List[Dict]:
    """Generate simple labels/actions per cluster."""
    summaries: List[Dict] = []
    for cid, group in clustered.groupby("cluster_id"):
        summary = {
            "cluster_id": int(cid),
            "size": len(group),
            "avg_amount": group["total_amount"].mean(),
            "avg_order_count": group["order_count"].mean(),
            "top_category": group["top_category"].mode().iat[0] if not group["top_category"].empty else "",
            "top_channel": group["top_channel"].mode().iat[0] if not group["top_channel"].empty else "",
            "top_device": group["top_device"].mode().iat[0] if not group["top_device"].empty else "",
        }
        # 简单规则生成动作建议
        if summary["avg_amount"] > clustered["total_amount"].mean():
            action = "高价值：会员权益+定向优惠"
        elif summary["avg_order_count"] > clustered["order_count"].mean():
            action = "高频：推送订阅与包月券"
        else:
            action = "普通：新品推荐+优惠券拉新"
        summary["action"] = action
        summaries.append(summary)
    summaries.sort(key=lambda x: x["cluster_id"])
    return summaries


def persist_cluster_profiles(clustered: pd.DataFrame) -> None:
    profiles = [
        UserClusterProfile(
            user_id=row.user_id,
            cluster_id=int(row.cluster_id),
            total_amount=Decimal(str(row.total_amount)),
            order_count=int(row.order_count),
            avg_amount=Decimal(str(row.avg_amount)),
            promo_ratio=Decimal(str(row.promo_ratio * 100)).quantize(Decimal("0.01")),
            refund_ratio=Decimal(str(row.refund_ratio * 100)).quantize(Decimal("0.01")),
            last_order_time=row.last_order_time.to_pydatetime(),
            top_category=row.top_category or "",
            top_channel=row.top_channel or "",
            top_device=row.top_device or "",
        )
        for row in clustered.itertuples(index=False)
    ]
    UserClusterProfile.objects.all().delete()
    UserClusterProfile.objects.bulk_create(profiles)


@transaction.atomic
def process_upload(
    uploaded_file,
    cluster_count: int = 4,
    auto_k: bool = False,
    auto_k_multi: bool = True,
    k_min: int = 2,
    k_max: int = 8,
) -> Tuple[List[Dict], List[Dict], Dict, Dict]:
    """Main pipeline: load CSV, persist orders, build features, cluster, persist profiles."""
    df = load_csv_to_df(uploaded_file)
    persist_orders(df)
    user_features = build_user_features(df)
    if auto_k:
        k_used, scores, method = choose_k_auto(user_features, k_min=k_min, k_max=k_max, multi_metric=auto_k_multi)
    else:
        k_used, scores, method = cluster_count, [], "manual"
    clustered, info = run_kmeans(user_features, n_clusters=k_used)
    persist_cluster_profiles(clustered)
    cluster_summaries = make_cluster_tags(clustered)
    sample_rows_raw = clustered.head(30).to_dict(orient="records")
    # ensure JSON-serializable for session storage
    sample_rows: List[Dict] = []
    for row in sample_rows_raw:
        converted = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                converted[k] = v.isoformat()
            else:
                converted[k] = v
        sample_rows.append(converted)
    # cluster均值用于可视化
    numeric_cols = [
        "total_amount",
        "order_count",
        "avg_amount",
        "promo_ratio",
        "refund_ratio",
        "recency_days",
    ]
    cluster_means = (
        clustered.groupby("cluster_id")[numeric_cols]
        .mean()
        .reset_index()
        .replace({np.nan: 0})
    )
    cluster_means_records = [
        {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v) for k, v in row.items()}
        for row in cluster_means.to_dict(orient="records")
    ]
    metrics = {
        "k_used": int(k_used),
        "k_auto": bool(auto_k),
        "k_range": [int(k_min), int(k_max)],
        "method": method,
        "inertia": float(info["inertia"]),
        "scores": scores,
    }
    chart_data = {
        "cluster_means": cluster_means_records,
    }
    return cluster_summaries, sample_rows, metrics, chart_data

