import pandas as pd
import numpy as np

def generate_synthetic_data(num_samples=5000):
    np.random.seed(42)
    
    data = []
    for _ in range(num_samples):
        # Decide category: 70% normal, 15% legitimate flash sale, 15% attack spike
        category = np.random.choice(['normal', 'flash_sale', 'attack'], p=[0.7, 0.15, 0.15])
        
        if category == 'normal':
            transaction_count = np.random.randint(1, 10)
            unique_ips = np.random.randint(1, 3)
            unique_devices = np.random.randint(1, 2)
            decline_rate = np.random.uniform(0.0, 0.1)
            current_amount = np.random.uniform(5.0, 100.0)
            average_amount = current_amount * np.random.uniform(0.9, 1.1)
            is_attack = 0
            
        elif category == 'flash_sale':
            # High volume, many unique users, low decline rate, higher amounts
            transaction_count = np.random.randint(100, 500)
            unique_ips = np.random.randint(80, 400)
            unique_devices = np.random.randint(50, 300)
            decline_rate = np.random.uniform(0.0, 0.05)
            current_amount = np.random.uniform(20.0, 200.0)
            average_amount = np.random.uniform(20.0, 200.0)
            is_attack = 0
            
        else:  # attack
            # High volume, very few unique IPs/devices, massive decline rate, tiny amounts
            transaction_count = np.random.randint(50, 300)
            unique_ips = np.random.randint(1, 3)
            unique_devices = np.random.randint(1, 2)
            decline_rate = np.random.uniform(0.85, 1.0)
            current_amount = np.random.uniform(1.0, 5.0)
            average_amount = np.random.uniform(1.5, 4.0)
            is_attack = 1

        amount_ratio = current_amount / average_amount if average_amount > 0 else 1.0
        hour_of_day = np.random.randint(0, 24)
        day_of_week = np.random.randint(1, 8)

        data.append({
            "transaction_count": transaction_count,
            "unique_ips": unique_ips,
            "unique_devices": unique_devices,
            "decline_rate": decline_rate,
            "current_amount": current_amount,
            "average_amount": average_amount,
            "amount_ratio": amount_ratio,
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
            "is_attack": is_attack
        })
        
    df = pd.DataFrame(data)
    df.to_csv("ml/data/transactions.csv", index=False)
    print("Generated 5,000 synthetic transaction patterns at ml/data/transactions.csv")

if __name__ == "__main__":
    import os
    os.makedirs("ml/data", exist_ok=True)
    generate_synthetic_data()