import pandas as pd
from xgboost import XGBClassifier
import joblib

def train_model():
    # 1. Load data
    df = pd.read_csv("ml/data/transactions.csv")
    
    X = df.drop(columns=["is_attack"])
    y = df["is_attack"]
    
    # 2. Train XGBoost Model
    print("Training XGBoost classifier...")
    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42
    )
    model.fit(X, y)
    
    # 3. Save model
    joblib.dump(model, "ml/model.pkl")
    print("Model successfully trained and saved to ml/model.pkl!")

if __name__ == "__main__":
    train_model()