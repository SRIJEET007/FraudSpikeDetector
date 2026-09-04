import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

def train_model():
    # 1. Load data
    df = pd.read_csv("ml/data/transactions.csv")
    
    feature_cols = [
        "transactionCount", "uniqueIps", "uniqueDevices",
        "declineRate", "currentAmount", "averageAmount",
        "amountRatio", "hourOfDay", "dayOfWeek"
    ]
    X = df[feature_cols]
    y = df["is_attack"]
    
    # 2. Train/test split for evaluation
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 3. Train XGBoost Model
    print("Training XGBoost classifier...")
    model = XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        scale_pos_weight=(y == 0).sum() / (y == 1).sum(),  # handle class imbalance
        random_state=42
    )
    model.fit(X_train, y_train)
    
    # 4. Evaluate
    y_pred = model.predict(X_test)
    print("\n--- Model Evaluation ---")
    print(classification_report(y_test, y_pred, target_names=["Normal", "Attack"]))

    # 5. Save model
    joblib.dump(model, "ml/model.pkl")
    print("Model saved to ml/model.pkl")

if __name__ == "__main__":
    train_model()