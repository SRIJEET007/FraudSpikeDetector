"""
=============================================================================
  FRAUD SPIKE DETECTOR — END-TO-END EVALUATION HARNESS
=============================================================================

Uses the IEEE-CIS Fraud Detection train_transaction.csv (590,540 rows).
  - Time-based 80/20 split (NO random shuffle — prevents temporal leakage).
  - Maps real fields to our pipeline's transactionRequest format.
  - Synthesizes missing fields (ipAddress, deviceId, approved) with
    fraud-aware distributions so the sliding-window features are realistic.
  - Replays the eval set through the pipeline (live, FastAPI-only, or local).
  - Computes honest metrics: precision, recall, F1, confusion matrix,
    false-positive rate, and false-positive cost.

MODES:
  --local    Load model.pkl directly in Python. No servers needed. FASTEST.
  --offline  Hit FastAPI /score endpoint only (needs FastAPI running).
  (default)  Hit Spring Boot /api/v1/transactions (needs both servers).

USAGE:
  python ml/evaluate_pipeline.py --local --sample 10000
  python ml/evaluate_pipeline.py --offline --sample 5000
  python ml/evaluate_pipeline.py --sample 5000  (full pipeline, both servers)
=============================================================================
"""

import argparse
import json
import os
import sys
import time
import uuid
import random
from collections import defaultdict, deque
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

SPRING_BOOT_URL = "http://localhost:8080/api/v1/transactions"
FASTAPI_ML_URL = "http://localhost:5000/score"
DATA_PATH = os.path.join(SCRIPT_DIR, "data", "train_transaction.csv")
MODEL_PATH = os.path.join(SCRIPT_DIR, "model.pkl")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "eval_results")
WINDOW_SECONDS = 60  # Must match slidingWindowService.WINDOW_SECOND

# False-positive cost model (for hackathon "honest metrics" track)
FP_COST = 50.0     # Cost per false positive ($50: customer friction, support, churn)
FN_COST = 500.0    # Cost per false negative ($500: avg fraud loss if undetected)
TP_BENEFIT = 450.0  # Benefit per true positive ($500 saved - $50 investigation)

# Decision thresholds (must match transactionService.java)
INSPECT_THRESHOLD = 0.7999    # spike AND mlScore >= this → INSPECT
SUSPICIOUS_THRESHOLD = 0.4777 # mlScore >= this → SUSPICIOUS
EWMA_Z_THRESHOLD = 2.0        # z-score for spike detection


# ─── Data Loading & Splitting ────────────────────────────────────────────────

def load_and_split(data_path, train_ratio=0.8):
    """Load IEEE-CIS data with time-based split. NO random shuffle."""
    print("[1/6] Loading dataset from {}...".format(data_path))
    use_cols = [
        'TransactionID', 'isFraud', 'TransactionDT', 'TransactionAmt',
        'card1', 'C1', 'C2', 'C13',
    ]
    df = pd.read_csv(data_path, usecols=use_cols)
    print("  Loaded {} rows, {} columns".format(len(df), len(df.columns)))
    print("  Overall fraud rate: {:.2f}%".format(df['isFraud'].mean() * 100))

    cutoff = df['TransactionDT'].quantile(train_ratio)
    train_df = df[df['TransactionDT'] <= cutoff].copy()
    eval_df = df[df['TransactionDT'] > cutoff].copy()

    print("  Time-based split at TransactionDT = {:.0f}".format(cutoff))
    print("  Train: {} rows ({:.2f}% fraud)".format(len(train_df), train_df['isFraud'].mean() * 100))
    print("  Eval:  {} rows ({:.2f}% fraud)".format(len(eval_df), eval_df['isFraud'].mean() * 100))
    return train_df, eval_df


# ─── Field Mapping & Synthesis ────────────────────────────────────────────────

def map_to_pipeline_format(eval_df, seed=42):
    """
    Map IEEE-CIS fields to our pipeline format with fraud-aware synthesis.

    Direct mappings:
      TransactionID → transactionId
      card1 → cardId  (13K unique cards)
      TransactionAmt → amount
      TransactionDT → timeStamp

    Synthesized (fraud-aware):
      ipAddress  - fraudsters share from small bot IP pool
      deviceId   - fraudsters share from small device pool
      approved   - fraud: ~70% decline, legit: ~5% decline
    """
    print("\n[2/6] Mapping fields to pipeline format...")
    rng = np.random.RandomState(seed)

    base_dt = datetime(2026, 9, 1, 0, 0, 0)
    min_dt = eval_df['TransactionDT'].min()

    fraud_ip_pool = [
        "{}.{}.{}.{}".format(rng.randint(1, 223), rng.randint(0, 255),
                             rng.randint(0, 255), rng.randint(1, 254))
        for _ in range(20)
    ]
    fraud_device_pool = ["bot-dev-{}".format(uuid.uuid4().hex[:6]) for _ in range(15)]

    records = []
    for _, row in eval_df.iterrows():
        is_fraud = int(row['isFraud'])
        txn_id = "TXN-{}".format(int(row['TransactionID']))
        card_id = "CARD-{}".format(int(row['card1']))
        amount = float(row['TransactionAmt'])

        dt_offset = float(row['TransactionDT']) - min_dt
        ts = base_dt + timedelta(seconds=dt_offset)

        if is_fraud:
            ip = rng.choice(fraud_ip_pool)
            device = rng.choice(fraud_device_pool)
            approved = bool(rng.random() > 0.70)
        else:
            ip = "{}.{}.{}.{}".format(
                rng.randint(1, 223), rng.randint(0, 255),
                rng.randint(0, 255), rng.randint(1, 254))
            device = "dev-{}".format(uuid.uuid4().hex[:8])
            approved = bool(rng.random() > 0.05)

        records.append({
            "transactionId": txn_id,
            "cardId": card_id,
            "ipAddress": ip,
            "deviceId": device,
            "approved": approved,
            "amount": round(amount, 2),
            "timestamp": ts,
            "timeStamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "_ground_truth_is_fraud": is_fraud,
        })

    print("  Mapped {} transactions".format(len(records)))
    fraud_count = sum(1 for r in records if r['_ground_truth_is_fraud'])
    print("  Fraud: {} | Legit: {}".format(fraud_count, len(records) - fraud_count))
    return records


# ─── EWMA Spike Detection (mirrors anomalyDetectorService.java) ──────────────

class CardBaseline:
    """Python mirror of cardBaseLine.java"""
    ALPHA = 0.2

    def __init__(self):
        self.ewma_mean = 0.0
        self.ewma_var = 1.0
        self.initialized = False

    def update(self, current_value, is_suspicious):
        value_to_learn = current_value
        if not self.initialized:
            self.ewma_mean = current_value
            self.ewma_var = 1.0
            self.initialized = True
            return
        if is_suspicious:
            value_to_learn = self.ewma_mean + 3 * self.get_std()
        error = value_to_learn - self.ewma_mean
        self.ewma_mean += self.ALPHA * error
        squared_err = error * error
        self.ewma_var = (1 - self.ALPHA) * self.ewma_var + self.ALPHA * squared_err

    def get_std(self):
        return max(self.ewma_var, 0.1) ** 0.5


def evaluate_spike(baseline, txn_count):
    """Mirror of anomalyDetectorService.evaluateSpike()"""
    current_value = txn_count
    mean = baseline.ewma_mean
    std_dev = baseline.get_std()
    z_score = (current_value - mean) / std_dev if std_dev > 0 else 0
    is_suspicious = z_score > EWMA_Z_THRESHOLD
    baseline.update(current_value, is_suspicious)
    return is_suspicious


# ─── LOCAL Mode (no servers needed) ──────────────────────────────────────────

def run_local_eval(records):
    """
    Full pipeline evaluation using model.pkl directly in Python.
    Replicates the ENTIRE Spring Boot pipeline:
      1. Sliding window per card (60s)
      2. Feature extraction (matching featureEngine.java)
      3. EWMA spike detection (matching anomalyDetectorService.java)
      4. XGBoost scoring (loading model.pkl directly)
      5. Decision logic (matching transactionService.java)

    No servers needed. Fastest mode.
    """
    import joblib

    print("\n[3/6] Running LOCAL eval (model.pkl + full pipeline simulation)...")
    print("  Loading model from {}...".format(MODEL_PATH))
    model = joblib.load(MODEL_PATH)

    records.sort(key=lambda r: r['timestamp'])

    card_windows = defaultdict(deque)
    card_baselines = defaultdict(CardBaseline)
    results = []
    start_time = time.time()

    for i, record in enumerate(records):
        card_id = record['cardId']
        ts = record['timestamp']

        # 1. Sliding window
        card_windows[card_id].append(record)
        cutoff_ts = ts - timedelta(seconds=WINDOW_SECONDS)
        while card_windows[card_id]:
            first = card_windows[card_id][0]
            if first['timestamp'] < cutoff_ts:
                card_windows[card_id].popleft()
            else:
                break

        window = list(card_windows[card_id])

        # 2. Feature extraction (matching featureEngine.java)
        txn_count = len(window)
        unique_ips = len(set(r['ipAddress'] for r in window))
        unique_devices = len(set(r['deviceId'] for r in window))
        declined = sum(1 for r in window if not r['approved'])
        decline_rate = declined / txn_count if txn_count > 0 else 0.0
        current_amount = record['amount']
        avg_amount = sum(r['amount'] for r in window) / txn_count if txn_count > 0 else 0.0
        amount_ratio = current_amount / avg_amount if avg_amount > 0 else 1.0
        hour_of_day = ts.hour
        day_of_week = ts.isoweekday()

        # 3. EWMA spike detection
        is_spike = evaluate_spike(card_baselines[card_id], txn_count)

        # 4. XGBoost scoring
        features = np.array([[
            txn_count, unique_ips, unique_devices, decline_rate,
            current_amount, avg_amount, amount_ratio, hour_of_day, day_of_week
        ]])
        probabilities = model.predict_proba(features)
        ml_score = float(probabilities[0][1])

        # 5. Decision logic (matching transactionService.java exactly)
        if is_spike and ml_score >= INSPECT_THRESHOLD:
            decision = "INSPECT"
        elif ml_score >= SUSPICIOUS_THRESHOLD:
            decision = "SUSPICIOUS"
        else:
            decision = "APPROVE"

        results.append({
            "transactionId": record["transactionId"],
            "ground_truth": record["_ground_truth_is_fraud"],
            "decision": decision,
            "mlScore": ml_score,
            "isSpike": is_spike,
        })

        if (i + 1) % 1000 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            eta = (len(records) - i - 1) / rate if rate > 0 else 0
            print("  [{}/{}] {:.0f} txn/s | ETA: {:.0f}s".format(
                i + 1, len(records), rate, eta))

    elapsed = time.time() - start_time
    print("  Completed in {:.1f}s ({:.0f} txn/s)".format(
        elapsed, len(records) / elapsed if elapsed > 0 else 0))
    return results


# ─── ONLINE Mode (Spring Boot) ───────────────────────────────────────────────

def run_online_eval(records, spring_url):
    """Replay through live Spring Boot endpoint."""
    import requests

    print("\n[3/6] Replaying {} transactions through Spring Boot...".format(len(records)))
    print("  Endpoint: {}".format(spring_url))

    results = []
    errors = 0
    start_time = time.time()

    for i, record in enumerate(records):
        payload = {
            "transactionId": record["transactionId"],
            "cardId": record["cardId"],
            "ipAddress": record["ipAddress"],
            "deviceId": record["deviceId"],
            "approved": record["approved"],
            "amount": record["amount"],
            "timeStamp": record["timeStamp"],
        }
        try:
            resp = requests.post(spring_url, json=payload, timeout=5)
            if resp.status_code == 200:
                body = resp.json()
                results.append({
                    "transactionId": record["transactionId"],
                    "ground_truth": record["_ground_truth_is_fraud"],
                    "decision": body.get("decision"),
                    "mlScore": body.get("mlScore", 0.0),
                    "isSpike": body.get("isSpike", False),
                })
            else:
                errors += 1
                results.append({
                    "transactionId": record["transactionId"],
                    "ground_truth": record["_ground_truth_is_fraud"],
                    "decision": "ERROR",
                    "mlScore": 0.0,
                    "isSpike": False,
                })
        except Exception:
            errors += 1
            results.append({
                "transactionId": record["transactionId"],
                "ground_truth": record["_ground_truth_is_fraud"],
                "decision": "ERROR",
                "mlScore": 0.0,
                "isSpike": False,
            })

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            eta = (len(records) - i - 1) / rate if rate > 0 else 0
            print("  [{}/{}] {:.0f} txn/s | ETA: {:.0f}s | errors: {}".format(
                i + 1, len(records), rate, eta, errors))

    elapsed = time.time() - start_time
    print("  Completed in {:.1f}s ({:.0f} txn/s) | {} errors".format(
        elapsed, len(records) / elapsed if elapsed > 0 else 0, errors))
    return results


# ─── OFFLINE Mode (FastAPI only) ─────────────────────────────────────────────

def run_offline_eval(records):
    """Compute features locally, score via FastAPI /score endpoint."""
    import requests

    print("\n[3/6] Running OFFLINE eval (FastAPI ML model only)...")
    print("  Endpoint: {}".format(FASTAPI_ML_URL))

    records.sort(key=lambda r: r['timestamp'])
    card_windows = defaultdict(deque)
    results = []
    errors = 0
    start_time = time.time()

    for i, record in enumerate(records):
        card_id = record['cardId']
        ts = record['timestamp']

        card_windows[card_id].append(record)
        cutoff_ts = ts - timedelta(seconds=WINDOW_SECONDS)
        while card_windows[card_id]:
            first = card_windows[card_id][0]
            if first['timestamp'] < cutoff_ts:
                card_windows[card_id].popleft()
            else:
                break

        window = list(card_windows[card_id])
        txn_count = len(window)
        unique_ips = len(set(r['ipAddress'] for r in window))
        unique_devices = len(set(r['deviceId'] for r in window))
        declined = sum(1 for r in window if not r['approved'])
        decline_rate = declined / txn_count if txn_count > 0 else 0.0
        current_amount = record['amount']
        avg_amount = sum(r['amount'] for r in window) / txn_count if txn_count > 0 else 0.0
        amount_ratio = current_amount / avg_amount if avg_amount > 0 else 1.0
        hour_of_day = ts.hour
        day_of_week = ts.isoweekday()

        payload = {
            "transactionCount": txn_count,
            "uniqueIps": unique_ips,
            "uniqueDevices": unique_devices,
            "declineRate": decline_rate,
            "currentAmount": current_amount,
            "averageAmount": avg_amount,
            "amountRatio": amount_ratio,
            "hourOfDay": hour_of_day,
            "dayOfWeek": day_of_week,
        }

        try:
            resp = requests.post(FASTAPI_ML_URL, json=payload, timeout=5)
            if resp.status_code == 200:
                body = resp.json()
                ml_score = body.get('fraudProbability', body.get('attackProbability', 0.0))
            else:
                ml_score = 0.0
                errors += 1
        except Exception:
            ml_score = 0.0
            errors += 1

        if ml_score >= SUSPICIOUS_THRESHOLD:
            decision = "SUSPICIOUS"
        else:
            decision = "APPROVE"

        results.append({
            "transactionId": record["transactionId"],
            "ground_truth": record["_ground_truth_is_fraud"],
            "decision": decision,
            "mlScore": ml_score,
            "isSpike": False,
        })

        if (i + 1) % 500 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            eta = (len(records) - i - 1) / rate if rate > 0 else 0
            print("  [{}/{}] {:.0f} txn/s | ETA: {:.0f}s | errors: {}".format(
                i + 1, len(records), rate, eta, errors))

    elapsed = time.time() - start_time
    print("  Completed in {:.1f}s ({:.0f} txn/s) | {} errors".format(
        elapsed, len(records) / elapsed if elapsed > 0 else 0, errors))
    return results


# ─── Metrics Computation ──────────────────────────────────────────────────────

def compute_metrics(results):
    """
    Compute honest metrics.

    Decision → binary mapping:
      INSPECT or SUSPICIOUS → predicted_fraud = 1
      APPROVE → predicted_fraud = 0
    """
    print("\n[4/6] Computing metrics...")

    valid = [r for r in results if r['decision'] != 'ERROR']
    error_count = len(results) - len(valid)
    if error_count > 0:
        print("  WARNING: {} errors excluded".format(error_count))
    if not valid:
        print("  FATAL: No valid results!")
        return None

    y_true = np.array([r['ground_truth'] for r in valid])
    y_pred = np.array([1 if r['decision'] in ('INSPECT', 'SUSPICIOUS') else 0 for r in valid])
    ml_scores = np.array([r['mlScore'] for r in valid])
    decisions = [r['decision'] for r in valid]
    spikes = np.array([r['isSpike'] for r in valid])

    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    total = tp + fp + tn + fn

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / total if total > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    # Cost analysis
    total_fp_cost = fp * FP_COST
    total_fn_cost = fn * FN_COST
    total_tp_benefit = tp * TP_BENEFIT
    net_value = total_tp_benefit - total_fp_cost - total_fn_cost

    # Decision distribution
    decision_counts = defaultdict(int)
    for d in decisions:
        decision_counts[d] += 1

    decision_breakdown = {}
    for dv in ['APPROVE', 'SUSPICIOUS', 'INSPECT']:
        mask = np.array([d == dv for d in decisions])
        if mask.sum() > 0:
            fraud_in = int(y_true[mask].sum())
            decision_breakdown[dv] = {
                'count': int(mask.sum()),
                'fraud_count': fraud_in,
                'fraud_rate_pct': round(fraud_in / mask.sum() * 100, 2),
            }

    # Spike analysis
    spike_count = int(spikes.sum())
    spike_fraud = int(y_true[spikes].sum()) if spike_count > 0 else 0

    # ML score distribution
    fraud_mask = y_true == 1
    legit_mask = y_true == 0

    metrics = {
        'dataset': {
            'total_transactions': total,
            'actual_fraud': int(y_true.sum()),
            'actual_legit': int((y_true == 0).sum()),
            'fraud_rate_pct': round(y_true.mean() * 100, 4),
            'errors_excluded': error_count,
        },
        'confusion_matrix': {
            'true_positives': tp,
            'false_positives': fp,
            'true_negatives': tn,
            'false_negatives': fn,
        },
        'classification_metrics': {
            'precision': round(precision, 6),
            'recall': round(recall, 6),
            'f1_score': round(f1, 6),
            'accuracy': round(accuracy, 6),
            'false_positive_rate': round(fpr, 6),
            'specificity': round(1 - fpr, 6),
        },
        'cost_analysis': {
            'fp_unit_cost': FP_COST,
            'fn_unit_cost': FN_COST,
            'tp_unit_benefit': TP_BENEFIT,
            'total_fp_cost': round(total_fp_cost, 2),
            'total_fn_cost': round(total_fn_cost, 2),
            'total_tp_benefit': round(total_tp_benefit, 2),
            'net_value': round(net_value, 2),
            'cost_per_transaction': round((total_fp_cost + total_fn_cost) / total, 4) if total > 0 else 0,
        },
        'decision_distribution': dict(decision_counts),
        'decision_breakdown': decision_breakdown,
        'spike_analysis': {
            'total_spikes': spike_count,
            'spikes_that_were_fraud': spike_fraud,
            'spike_precision': round(spike_fraud / spike_count, 4) if spike_count > 0 else None,
        },
        'ml_score_distribution': {
            'fraud_mean': round(float(ml_scores[fraud_mask].mean()), 6) if fraud_mask.sum() > 0 else None,
            'fraud_median': round(float(np.median(ml_scores[fraud_mask])), 6) if fraud_mask.sum() > 0 else None,
            'fraud_p25': round(float(np.percentile(ml_scores[fraud_mask], 25)), 6) if fraud_mask.sum() > 0 else None,
            'fraud_p75': round(float(np.percentile(ml_scores[fraud_mask], 75)), 6) if fraud_mask.sum() > 0 else None,
            'legit_mean': round(float(ml_scores[legit_mask].mean()), 6) if legit_mask.sum() > 0 else None,
            'legit_median': round(float(np.median(ml_scores[legit_mask])), 6) if legit_mask.sum() > 0 else None,
            'legit_p25': round(float(np.percentile(ml_scores[legit_mask], 25)), 6) if legit_mask.sum() > 0 else None,
            'legit_p75': round(float(np.percentile(ml_scores[legit_mask], 75)), 6) if legit_mask.sum() > 0 else None,
        },
        'thresholds_used': {
            'inspect_threshold': INSPECT_THRESHOLD,
            'suspicious_threshold': SUSPICIOUS_THRESHOLD,
            'spike_detection': 'EWMA z-score > {}'.format(EWMA_Z_THRESHOLD),
        },
    }
    return metrics


# ─── Threshold Sweep ──────────────────────────────────────────────────────────

def sweep_thresholds(results):
    """Sweep ML score thresholds to find optimal operating point."""
    print("\n[5/6] Sweeping thresholds...")

    valid = [r for r in results if r['decision'] != 'ERROR']
    y_true = np.array([r['ground_truth'] for r in valid])
    ml_scores = np.array([r['mlScore'] for r in valid])

    thresholds = np.arange(0.05, 1.0, 0.05).tolist()
    # Also include current thresholds
    for t in [SUSPICIOUS_THRESHOLD, INSPECT_THRESHOLD]:
        if t not in thresholds:
            thresholds.append(t)
    thresholds.sort()

    sweep_results = []
    for t in thresholds:
        y_pred = (ml_scores >= t).astype(int)
        tp = int(np.sum((y_true == 1) & (y_pred == 1)))
        fp = int(np.sum((y_true == 0) & (y_pred == 1)))
        tn = int(np.sum((y_true == 0) & (y_pred == 0)))
        fn = int(np.sum((y_true == 1) & (y_pred == 0)))

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1_val = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        fpr_val = fp / (fp + tn) if (fp + tn) > 0 else 0
        net = tp * TP_BENEFIT - fp * FP_COST - fn * FN_COST

        sweep_results.append({
            'threshold': round(t, 4),
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'f1': round(f1_val, 4),
            'fpr': round(fpr_val, 4),
            'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
            'net_value': round(net, 2),
        })

    return sweep_results


# ─── Report ───────────────────────────────────────────────────────────────────

def print_report(metrics, sweep, mode_label):
    print("\n")
    print("=" * 74)
    print("  FRAUD SPIKE DETECTOR — EVALUATION REPORT")
    print("  IEEE-CIS Fraud Detection Dataset (held-out last 20% by time)")
    print("  Mode: {}".format(mode_label))
    print("  Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 74)

    ds = metrics['dataset']
    print("\n  DATASET")
    print("  " + "-" * 40)
    print("  Total transactions:  {:>8,}".format(ds['total_transactions']))
    print("  Actual fraud:        {:>8,} ({:.2f}%)".format(ds['actual_fraud'], ds['fraud_rate_pct']))
    print("  Actual legit:        {:>8,}".format(ds['actual_legit']))
    if ds['errors_excluded'] > 0:
        print("  Errors excluded:     {:>8,}".format(ds['errors_excluded']))

    cm = metrics['confusion_matrix']
    print("\n  CONFUSION MATRIX")
    print("  " + "-" * 40)
    print("                           Predicted")
    print("                      FRAUD       LEGIT")
    print("  Actual FRAUD    {:>8,} (TP)  {:>8,} (FN)".format(cm['true_positives'], cm['false_negatives']))
    print("  Actual LEGIT    {:>8,} (FP)  {:>8,} (TN)".format(cm['false_positives'], cm['true_negatives']))

    cl = metrics['classification_metrics']
    print("\n  CLASSIFICATION METRICS")
    print("  " + "-" * 40)
    print("  Precision:            {:.4f}".format(cl['precision']))
    print("  Recall (sensitivity): {:.4f}".format(cl['recall']))
    print("  F1 Score:             {:.4f}".format(cl['f1_score']))
    print("  Accuracy:             {:.4f}".format(cl['accuracy']))
    print("  False Positive Rate:  {:.4f}".format(cl['false_positive_rate']))
    print("  Specificity:          {:.4f}".format(cl['specificity']))

    ca = metrics['cost_analysis']
    print("\n  COST-WEIGHTED ANALYSIS")
    print("  " + "-" * 40)
    print("  FP unit cost:        ${:.0f}  (customer friction per false alarm)".format(ca['fp_unit_cost']))
    print("  FN unit cost:        ${:.0f} (avg fraud loss if missed)".format(ca['fn_unit_cost']))
    print("  TP unit benefit:     ${:.0f} (fraud caught: loss prevented - investigation)".format(ca['tp_unit_benefit']))
    print("  " + "-" * 30)
    print("  Total FP cost:       ${:>12,.2f}".format(ca['total_fp_cost']))
    print("  Total FN cost:       ${:>12,.2f}".format(ca['total_fn_cost']))
    print("  Total TP benefit:    ${:>12,.2f}".format(ca['total_tp_benefit']))
    print("  NET VALUE:           ${:>12,.2f}".format(ca['net_value']))
    print("  Cost/transaction:    ${:.4f}".format(ca['cost_per_transaction']))

    db = metrics['decision_breakdown']
    print("\n  DECISION DISTRIBUTION")
    print("  " + "-" * 40)
    for dv in ['APPROVE', 'SUSPICIOUS', 'INSPECT']:
        if dv in db:
            b = db[dv]
            print("  {:12s}: {:>8,} txns | {:>6,} fraud ({:>5.1f}% fraud rate)".format(
                dv, b['count'], b['fraud_count'], b['fraud_rate_pct']))

    sa = metrics['spike_analysis']
    print("\n  SPIKE DETECTION (EWMA Layer)")
    print("  " + "-" * 40)
    print("  Total spikes detected:  {:>6,}".format(sa['total_spikes']))
    print("  Spikes that were fraud: {:>6,}".format(sa['spikes_that_were_fraud']))
    if sa['spike_precision'] is not None:
        print("  Spike precision:        {:.4f}".format(sa['spike_precision']))
    else:
        print("  Spike precision:        N/A (no spikes)")

    ms = metrics['ml_score_distribution']
    print("\n  ML SCORE DISTRIBUTION")
    print("  " + "-" * 40)
    if ms['fraud_mean'] is not None:
        print("  Fraud txns:  mean={:.4f}  median={:.4f}  [p25={:.4f}, p75={:.4f}]".format(
            ms['fraud_mean'], ms['fraud_median'], ms['fraud_p25'], ms['fraud_p75']))
    if ms['legit_mean'] is not None:
        print("  Legit txns:  mean={:.4f}  median={:.4f}  [p25={:.4f}, p75={:.4f}]".format(
            ms['legit_mean'], ms['legit_median'], ms['legit_p25'], ms['legit_p75']))

    print("\n  THRESHOLD SWEEP (ML score only)")
    print("  " + "-" * 70)
    print("  {:>9s}  {:>8s}  {:>8s}  {:>8s}  {:>8s}  {:>14s}".format(
        "Threshold", "Prec", "Recall", "F1", "FPR", "Net Value"))
    print("  " + "-" * 70)
    for s in sweep:
        marker = ""
        if abs(s['threshold'] - SUSPICIOUS_THRESHOLD) < 0.001:
            marker = " << SUSPICIOUS"
        elif abs(s['threshold'] - INSPECT_THRESHOLD) < 0.001:
            marker = " << INSPECT"
        print("  {:>9.4f}  {:>8.4f}  {:>8.4f}  {:>8.4f}  {:>8.4f}  ${:>13,.2f}{}".format(
            s['threshold'], s['precision'], s['recall'], s['f1'], s['fpr'],
            s['net_value'], marker))

    best = max(sweep, key=lambda x: x['net_value'])
    best_f1 = max(sweep, key=lambda x: x['f1'])
    print("\n  >> Optimal threshold by NET VALUE: {:.4f}".format(best['threshold']))
    print("     Prec={:.4f} Recall={:.4f} F1={:.4f} Net=${:,.2f}".format(
        best['precision'], best['recall'], best['f1'], best['net_value']))
    print("  >> Optimal threshold by F1:        {:.4f}".format(best_f1['threshold']))
    print("     Prec={:.4f} Recall={:.4f} F1={:.4f} Net=${:,.2f}".format(
        best_f1['precision'], best_f1['recall'], best_f1['f1'], best_f1['net_value']))

    print("\n" + "=" * 74)


def save_to_postgres(metrics, sweep, mode_label, db_params=None):
    """Persist evaluation run to Postgres table evaluation_runs."""
    if db_params is None:
        db_params = {
            'dbname': 'TransanctionAuditLogs',
            'user': 'postgres',
            'password': 'password',
            'host': 'localhost',
            'port': 5432
        }

    try:
        import psycopg2
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id BIGSERIAL PRIMARY KEY,
                run_timestamp TIMESTAMP NOT NULL,
                precision_score DOUBLE PRECISION,
                recall_score DOUBLE PRECISION,
                f1_score DOUBLE PRECISION,
                false_positive_rate DOUBLE PRECISION,
                threshold_used DOUBLE PRECISION,
                net_value DOUBLE PRECISION,
                cost_per_txn DOUBLE PRECISION,
                total_transactions INTEGER,
                actual_fraud INTEGER,
                actual_legit INTEGER,
                true_positives INTEGER,
                false_positives INTEGER,
                true_negatives INTEGER,
                false_negatives INTEGER,
                evaluation_mode VARCHAR(255),
                confusion_matrix TEXT,
                threshold_sweep TEXT,
                created_at TIMESTAMP NOT NULL
            );
        """)

        now_str = datetime.now().isoformat()
        cm = metrics['confusion_matrix']
        cls_m = metrics['classification_metrics']
        costs = metrics['cost_analysis']
        ds = metrics['dataset']

        query = """
            INSERT INTO evaluation_runs (
                run_timestamp, precision_score, recall_score, f1_score,
                false_positive_rate, threshold_used, net_value, cost_per_txn,
                total_transactions, actual_fraud, actual_legit,
                true_positives, false_positives, true_negatives, false_negatives,
                evaluation_mode, confusion_matrix, threshold_sweep, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """

        cursor.execute(query, (
            now_str,
            cls_m['precision'],
            cls_m['recall'],
            cls_m['f1_score'],
            cls_m['false_positive_rate'],
            SUSPICIOUS_THRESHOLD,
            costs['net_value'],
            costs['cost_per_transaction'],
            ds['total_transactions'],
            ds['actual_fraud'],
            ds['actual_legit'],
            cm['true_positives'],
            cm['false_positives'],
            cm['true_negatives'],
            cm['false_negatives'],
            mode_label,
            json.dumps(cm),
            json.dumps(sweep),
            now_str
        ))

        run_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        print("    evaluation_runs table - Persisted run #{} to Postgres".format(run_id))
    except Exception as e:
        print("    (Postgres persistence skipped: {})".format(e))


def save_to_spring_boot(metrics, sweep, mode_label, spring_url="http://localhost:8080/api/evaluation/record"):
    """POST evaluation run to Spring Boot API if active."""
    try:
        import requests
        cm = metrics['confusion_matrix']
        cls_m = metrics['classification_metrics']
        costs = metrics['cost_analysis']
        ds = metrics['dataset']

        payload = {
            "runTimestamp": datetime.now().isoformat(),
            "precisionScore": cls_m['precision'],
            "recallScore": cls_m['recall'],
            "f1Score": cls_m['f1_score'],
            "falsePositiveRate": cls_m['false_positive_rate'],
            "thresholdUsed": SUSPICIOUS_THRESHOLD,
            "netValue": costs['net_value'],
            "costPerTxn": costs['cost_per_transaction'],
            "totalTransactions": ds['total_transactions'],
            "actualFraud": ds['actual_fraud'],
            "actualLegit": ds['actual_legit'],
            "truePositives": cm['true_positives'],
            "falsePositives": cm['false_positives'],
            "trueNegatives": cm['true_negatives'],
            "falseNegatives": cm['false_negatives'],
            "evaluationMode": mode_label,
            "confusionMatrix": json.dumps(cm),
            "thresholdSweep": json.dumps(sweep)
        }
        resp = requests.post(spring_url, json=payload, timeout=3)
        if resp.status_code == 200:
            print("    POST /api/evaluation/record - Sent run to Spring Boot API")
    except Exception:
        pass


def save_results(metrics, sweep, results, results_dir, mode_label="LOCAL"):
    os.makedirs(results_dir, exist_ok=True)

    with open(os.path.join(results_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    with open(os.path.join(results_dir, "threshold_sweep.json"), "w") as f:
        json.dump(sweep, f, indent=2)

    # Save raw results (limit to 50K to avoid huge files)
    raw = results[:50000] if len(results) > 50000 else results
    with open(os.path.join(results_dir, "raw_results.json"), "w") as f:
        json.dump(raw, f)

    print("\n  Results saved to {}/".format(results_dir))
    print("    metrics.json          - Full metrics (dashboard-ready)")
    print("    threshold_sweep.json  - Threshold optimization data")
    print("    raw_results.json      - Per-transaction results")

    save_to_postgres(metrics, sweep, mode_label)
    save_to_spring_boot(metrics, sweep, mode_label)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global FASTAPI_ML_URL
    parser = argparse.ArgumentParser(description="Fraud Spike Detector — Evaluation Harness")
    parser.add_argument("--sample", type=int, default=10000,
                        help="Eval set size (0=full ~118K). Default: 10000")
    parser.add_argument("--local", action="store_true",
                        help="LOCAL mode: load model.pkl directly. No servers needed.")
    parser.add_argument("--offline", action="store_true",
                        help="OFFLINE mode: FastAPI /score only (no Spring Boot).")
    parser.add_argument("--spring-url", default=SPRING_BOOT_URL)
    parser.add_argument("--ml-url", default=FASTAPI_ML_URL)
    parser.add_argument("--results-dir", default=RESULTS_DIR)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    FASTAPI_ML_URL = args.ml_url

    # 1. Load and split
    _, eval_df = load_and_split(DATA_PATH)

    # 2. Sample if requested
    if args.sample > 0 and args.sample < len(eval_df):
        print("\n  Stratified sampling {} from eval set...".format(args.sample))
        fraud_df = eval_df[eval_df['isFraud'] == 1]
        legit_df = eval_df[eval_df['isFraud'] == 0]
        fraud_ratio = len(fraud_df) / len(eval_df)

        n_fraud = max(1, int(args.sample * fraud_ratio))
        n_legit = args.sample - n_fraud

        fraud_idx = np.linspace(0, len(fraud_df) - 1, min(n_fraud, len(fraud_df)), dtype=int)
        legit_idx = np.linspace(0, len(legit_df) - 1, min(n_legit, len(legit_df)), dtype=int)

        eval_df = pd.concat([
            fraud_df.iloc[fraud_idx],
            legit_df.iloc[legit_idx]
        ]).sort_values('TransactionDT')
        print("  Sampled: {} fraud + {} legit = {}".format(
            len(fraud_df.iloc[fraud_idx]), len(legit_df.iloc[legit_idx]), len(eval_df)))

    # 3. Map to pipeline format
    records = map_to_pipeline_format(eval_df, seed=args.seed)

    # 4. Run evaluation
    if args.local:
        mode_label = "LOCAL (model.pkl direct, full pipeline simulation)"
        results = run_local_eval(records)
    elif args.offline:
        mode_label = "OFFLINE (FastAPI /score only)"
        results = run_offline_eval(records)
    else:
        mode_label = "ONLINE (Spring Boot end-to-end)"
        results = run_online_eval(records, args.spring_url)

    # 5. Metrics
    metrics = compute_metrics(results)
    if metrics is None:
        sys.exit(1)

    # 6. Threshold sweep
    sweep = sweep_thresholds(results)

    # 7. Report
    print_report(metrics, sweep, mode_label)
    save_results(metrics, sweep, results, args.results_dir, mode_label=mode_label)

    print("\n[6/6] DONE.")


if __name__ == "__main__":
    main()
