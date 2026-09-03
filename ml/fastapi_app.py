import os
from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np

app = FastAPI(title="Fraud ML Scoring Service")

# Load trained model on startup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model.pkl")
model = joblib.load(MODEL_PATH)

@app.get("/")
@app.get("/health")
def health_check():
    return {
        "status": "UP",
        "service": "Fraud ML Scoring Service",
        "model_loaded": model is not None
    }

class FeatureRequest(BaseModel):
    transactionCount: int
    uniqueIps: int
    uniqueDevices: int
    declineRate: float
    currentAmount: float
    averageAmount: float
    amountRatio: float
    hourOfDay: int
    dayOfWeek: int

@app.post("/score")
def score_transaction(features: FeatureRequest):
    # Construct feature array matching the training order
    X = np.array([[
        features.transactionCount,
        features.uniqueIps,
        features.uniqueDevices,
        features.declineRate,
        features.currentAmount,
        features.averageAmount,
        features.amountRatio,
        features.hourOfDay,
        features.dayOfWeek
    ]])
    
    # Predict probability of class 1 (Attack)
    probabilities = model.predict_proba(X)
    attack_probability = float(probabilities[0][1])
    
    return {
        "attackProbability": attack_probability
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)