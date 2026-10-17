"""
Solaron Anomaly Model Evaluation Framework (Phase 5, Task 20).

Rigorously benchmarks algorithmic anomaly detection and fault classification against
two ground-truth label sources:
1. Hardware inverter fault codes logged in inverter_snapshots
2. Field technician validation feedback logged in anomaly_feedback

Calculates Precision, Recall, F1 Score, and False Positive Rate to replace guess-work
with empirical validation metrics.
"""

import logging
from typing import Any, Dict, List, Optional
import pandas as pd
try:
    from pipeline import db
except ImportError:
    import db

logger = logging.getLogger(__name__)


def evaluate_anomaly_model(month_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Evaluate statistical & ML anomaly flags against hardware fault codes and technician labels.
    """
    db.init_db()

    # 1. Fetch monthly generation flags
    sql = """
    SELECT plant_id, month, kwh, pr_pct, tier, anomaly_score, anomaly_flag
    FROM monthly_generation
    WHERE kwh > 1.0
    """
    params = []
    if month_str:
        sql += " AND month = ?"
        params.append(month_str)

    df_monthly = db.query_df(sql, params, db="analytics")
    if df_monthly.empty:
        return {
            "total_evaluated": 0,
            "anomalies_flagged": 0,
            "precision": 0.0,
            "recall": 0.0,
            "f1_score": 0.0,
            "details": "No monthly data available",
        }

    # 2. Fetch ground-truth feedback labels
    feedback_list = db.get_anomaly_feedback()
    feedback_map = {}
    for fb in feedback_list:
        key = (fb["plant_id"], fb["date_or_month"])
        feedback_map[key] = fb["technician_label"].lower().strip()

    # 3. Fetch hardware fault codes from snapshots
    snap_sql = """
    SELECT DISTINCT plant_id, strftime('%Y-%m', snapshot_ts) as s_month
    FROM inverter_snapshots
    WHERE fault_code IS NOT NULL AND fault_code != '' AND fault_code != '0';
    """
    snap_df = db.query_df(snap_sql, db="analytics")
    hardware_fault_keys = set()
    if not snap_df.empty:
        for _, row in snap_df.iterrows():
            hardware_fault_keys.add((str(row["plant_id"]), str(row["s_month"])))

    # Compute evaluation metrics
    tp = 0  # Flagged and verified true fault
    fp = 0  # Flagged and verified false alarm
    fn = 0  # Not flagged and had verified true fault
    tn = 0  # Not flagged and verified normal
    unlabeled_flagged = 0
    unlabeled_unflagged = 0

    for _, row in df_monthly.iterrows():
        key = (str(row["plant_id"]), str(row["month"]))
        is_ml_flag = int(row.get("anomaly_flag", 0)) == 1
        is_tier_flag = str(row.get("tier")) in ("Critical", "Needs Attention")
        flagged = is_ml_flag or is_tier_flag

        # Check ground truth
        has_hw_fault = key in hardware_fault_keys
        tech_label = feedback_map.get(key)

        is_true_fault = has_hw_fault or (tech_label in ("real_fault", "fault", "confirmed", "true_positive"))
        is_false_alarm = tech_label in ("false_alarm", "normal", "healthy", "false_positive")
        is_labeled = is_true_fault or is_false_alarm

        if is_labeled:
            if flagged:
                if is_true_fault:
                    tp += 1
                else:
                    fp += 1
            else:
                if is_true_fault:
                    fn += 1
                else:
                    tn += 1
        else:
            if flagged:
                unlabeled_flagged += 1
            else:
                unlabeled_unflagged += 1

    labeled_total = tp + fp + fn + tn
    total_eval = len(df_monthly)
    coverage_pct = round((labeled_total / max(total_eval, 1)) * 100.0, 1)

    precision = round(tp / (tp + fp), 3) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 3) if (tp + fn) > 0 else 0.0
    f1 = round(2 * (precision * recall) / (precision + recall), 3) if (precision + recall) > 0 else 0.0
    fpr = round(fp / (fp + tn), 3) if (fp + tn) > 0 else 0.0

    return {
        "total_evaluated": total_eval,
        "labeled_count": labeled_total,
        "coverage_pct": coverage_pct,
        "anomalies_flagged": (tp + fp + unlabeled_flagged),
        "unlabeled_flags": unlabeled_flagged,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "precision": precision,
        "precision_pct": round(precision * 100, 1),
        "recall": recall,
        "recall_pct": round(recall * 100, 1),
        "f1_score": f1,
        "false_positive_rate": fpr,
    }
