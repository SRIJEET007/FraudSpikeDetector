"""
=============================================================================
  Retrain the XGBoost model on IEEE-CIS data mapped to our feature space.
=============================================================================

This script:
  1. Loads train_transaction.csv (first 80% by TransactionDT)
  2. Simulates the sliding-window feature extraction our pipeline uses
  3. Trains XGBoost on these mapped features
  4. Saves model.pkl (production model used by FastAPI)
  5. Reports training metrics as a sanity check

The key insight: our pipeline computes per-card windowed features
(transactionCount, uniqueIps, etc.), not the raw IEEE-CIS features.
So we must simulate the windowed aggregation to train on the right
feature space.
=============================================================================
"""

import os
import uuid
import time
import random
from collections import defaultdict, deque
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, confusion_matrix
import joblib

# ─── Configuration ───────────────────────────────────────────────────────────

DATA_PATH = "ml/data/train_transaction.csv"
MODEL_PATH = "ml/model.pkl"
TRAIN_RATIO = 0.8
WINDOW_SECONDS = 60  # Must match slidingWindowService.WINDOW_SECOND
SEED = 42

np.random.seed(SEED)
random.seed(SEED)


def load_data():
    """Load IEEE-CIS and time-split."""
    print("[1/4] Loading IEEE-CIS data...")
    use_cols = [
        'TransactionID', 'isFraud', 'TransactionDT', 'TransactionAmt',
        'card1', 'C1', 'C2', 'C13',
    ]
    df = pd.read_csv(DATA_PATH, usecols=use_cols)

    cutoff = df['TransactionDT'].quantile(TRAIN_RATIO)
    train_df = df[df['TransactionDT'] <= cutoff].copy()
    test_df = df[df['TransactionDT'] > cutoff].copy()

    print("  Train: {} rows ({:.2f}% fraud)".format(len(train_df), train_df['isFraud'].mean() * 100))
    print("  Test:  {} rows ({:.2f}% fraud)".format(len(test_df), test_df['isFraud'].mean() * 100))
    return train_df, test_df


def synthesize_raw_transactions(df, label="train"):
    """
    Convert each IEEE-CIS row into a raw transaction with synthesized
    network fields (IP, device, approved) based on fraud-aware distributions.
    Returns list of dicts sorted by timestamp.
    """
    print("\n[2/4] Synthesizing raw transactions ({})...".format(label))
    rng = np.random.RandomState(SEED if label == "train" else SEED + 1)

    base_dt = datetime(2026, 9, 1)
    min_dt = df['TransactionDT'].min()

    # Bot IP/device pools
    fraud_ips = [
        "{}.{}.{}.{}".format(rng.randint(1, 223), rng.randint(0, 255),
                             rng.randint(0, 255), rng.randint(1, 254))
        for _ in range(20)
    ]
    fraud_devices = ["bot-{}".format(uuid.uuid4().hex[:6]) for _ in range(15)]

    records = []
    for _, row in df.iterrows():
        is_fraud = int(row['isFraud'])
        dt_offset = float(row['TransactionDT']) - min_dt
        ts = base_dt + timedelta(seconds=dt_offset)

        card_id = "CARD-{}".format(int(row['card1']))
        amount = float(row['TransactionAmt'])

        if is_fraud:
            ip = rng.choice(fraud_ips)
            device = rng.choice(fraud_devices)
            approved = bool(rng.random() > 0.70)
        else:
            ip = "{}.{}.{}.{}".format(
                rng.randint(1, 223), rng.randint(0, 255),
                rng.randint(0, 255), rng.randint(1, 254))
            device = "dev-{}".format(uuid.uuid4().hex[:8])
            approved = bool(rng.random() > 0.05)

        records.append({
            'cardId': card_id,
            'ipAddress': ip,
            'deviceId': device,
            'approved': approved,
            'amount': amount,
            'timestamp': ts,
            'is_fraud': is_fraud,
        })

    records.sort(key=lambda r: r['timestamp'])
    print("  Synthesized {} records".format(len(records)))
    return records


def compute_windowed_features(records, sample_size=None):
    """
    Simulate the sliding-window feature extraction that our Spring Boot
    featureEngine.java does. This ensures the training features match
    what the model sees in production.
    """
    print("\n[3/4] Computing sliding-window features...")

    if sample_size and len(records) > sample_size:
        # Stratified sampling for speed during training
        fraud_records = [r for r in records if r['is_fraud'] == 1]
        legit_records = [r for r in records if r['is_fraud'] == 0]
        fraud_ratio = len(fraud_records) / len(records)

        n_fraud = max(1, int(sample_size * fraud_ratio))
        n_legit = sample_size - n_fraud

        # Evenly spaced (preserves time ordering)
        fraud_idx = np.linspace(0, len(fraud_records) - 1, min(n_fraud, len(fraud_records)), dtype=int)
        legit_idx = np.linspace(0, len(legit_records) - 1, min(n_legit, len(legit_records)), dtype=int)

        sampled = [fraud_records[i] for i in fraud_idx] + [legit_records[i] for i in legit_idx]
        sampled.sort(key=lambda r: r['timestamp'])
        records = sampled
        print("  Sampled to {} records for training speed".format(len(records)))

    card_windows = defaultdict(deque)
    features = []
    labels = []

    start = time.time()
    for i, rec in enumerate(records):
        card_id = rec['cardId']
        ts = rec['timestamp']

        # Add to window
        card_windows[card_id].append(rec)

        # Evict old (60-second window)
        cutoff_ts = ts - timedelta(seconds=WINDOW_SECONDS)
        while card_windows[card_id]:
            first = card_windows[card_id][0]
            if first['timestamp'] < cutoff_ts:
                card_windows[card_id].popleft()
            else:
                break

        window = list(card_windows[card_id])

        # Compute features (matching featureEngine.java exactly)
        txn_count = len(window)
        unique_ips = len(set(r['ipAddress'] for r in window))
        unique_devices = len(set(r['deviceId'] for r in window))
        declined = sum(1 for r in window if not r['approved'])
        decline_rate = declined / txn_count if txn_count > 0 else 0.0
        current_amount = rec['amount']
        avg_amount = sum(r['amount'] for r in window) / txn_count if txn_count > 0 else 0.0
        amount_ratio = current_amount / avg_amount if avg_amount > 0 else 1.0
        hour_of_day = ts.hour
        day_of_week = ts.isoweekday()

        features.append([
            txn_count, unique_ips, unique_devices, decline_rate,
            current_amount, avg_amount, amount_ratio, hour_of_day, day_of_week
        ])
        labels.append(rec['is_fraud'])

        if (i + 1) % 10000 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            print("  [{}/{}] {:.0f} rec/s".format(i + 1, len(records), rate))

    feature_cols = [
        "transactionCount", "uniqueIps", "uniqueDevices", "declineRate",
        "currentAmount", "averageAmount", "amountRatio", "hourOfDay", "dayOfWeek"
    ]

    X = pd.DataFrame(features, columns=feature_cols)
    y = np.array(labels)

    print("  Features shape: {}".format(X.shape))
    print("  Fraud rate: {:.2f}%".format(y.mean() * 100))

    return X, y


def train_and_evaluate(X_train, y_train, X_test, y_test):
    """Train XGBoost and report metrics."""
    print("\n[4/4] Training XGBoost classifier...")

    scale_pos = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    print("  scale_pos_weight: {:.2f}".format(scale_pos))

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=scale_pos,
        random_state=SEED,
        eval_metric='logloss',
    )

    model.fit(X_train, y_train)

    # Evaluate on test set
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    print("\n--- Model Evaluation on Held-Out Test Set ---")
    print(classification_report(y_test, y_pred, target_names=["Normal", "Attack"]))

    cm = confusion_matrix(y_test, y_pred)
    print("Confusion Matrix:")
    print("                Predicted Normal  Predicted Attack")
    print("  Actual Normal    {:>8d}          {:>8d}".format(cm[0][0], cm[0][1]))
    print("  Actual Attack    {:>8d}          {:>8d}".format(cm[1][0], cm[1][1]))

    # Feature importance
    importances = model.feature_importances_
    feature_names = X_train.columns
    sorted_idx = np.argsort(importances)[::-1]
    print("\nFeature Importance:")
    for idx in sorted_idx:
        print("  {:20s}: {:.4f}".format(feature_names[idx], importances[idx]))

    # Save
    joblib.dump(model, MODEL_PATH)
    print("\nModel saved to {}".format(MODEL_PATH))

    return model


def main():
    train_df, test_df = load_data()

    # For training speed, sample to 100K records (stratified)
    # Full 472K would take too long for the windowed feature computation
    print("\n--- Training Set ---")
    train_records = synthesize_raw_transactions(train_df, "train")
    X_train, y_train = compute_windowed_features(train_records, sample_size=100000)

    print("\n--- Test Set ---")
    test_records = synthesize_raw_transactions(test_df, "test")
    X_test, y_test = compute_windowed_features(test_records, sample_size=20000)

    train_and_evaluate(X_train, y_train, X_test, y_test)


if __name__ == "__main__":
    main()
