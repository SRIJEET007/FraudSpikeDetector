import pandas as pd
import numpy as np

def generate_synthetic_data(num_samples=10000):
    np.random.seed(42)
    
    data = []
    for _ in range(num_samples):
        # 65% normal, 15% flash sale (legit spike), 20% attack
        category = np.random.choice(['normal', 'flash_sale', 'attack'], p=[0.65, 0.15, 0.20])
        
        if category == 'normal':
            # Low volume, 1-2 IPs/devices, low decline, moderate amounts
            transaction_count = np.random.randint(1, 15)
            unique_ips = np.random.randint(1, 3)
            unique_devices = np.random.randint(1, 2)
            decline_rate = np.random.uniform(0.0, 0.15)
            current_amount = np.random.uniform(10.0, 300.0)
            average_amount = current_amount * np.random.uniform(0.85, 1.15)
            is_attack = 0
            
        elif category == 'flash_sale':
            # High volume, MANY unique IPs/devices (legit users), low decline, normal amounts
            transaction_count = np.random.randint(80, 500)
            unique_ips = np.random.randint(60, 450)
            unique_devices = np.random.randint(50, 400)
            decline_rate = np.random.uniform(0.0, 0.08)
            current_amount = np.random.uniform(20.0, 500.0)
            average_amount = np.random.uniform(20.0, 500.0)
            is_attack = 0
            
        else:  # attack - two realistic subtypes
            attack_type = np.random.choice(['card_testing', 'account_takeover'], p=[0.5, 0.5])
            
            if attack_type == 'card_testing':
                # Many rapid txns, FEW IPs/devices (bot), HIGH decline, tiny probe amounts
                transaction_count = np.random.randint(20, 150)
                unique_ips = np.random.randint(1, 4)
                unique_devices = np.random.randint(1, 3)
                decline_rate = np.random.uniform(0.70, 1.0)
                current_amount = np.random.uniform(0.50, 10.0)
                average_amount = np.random.uniform(0.50, 10.0)
            else:
                # Account takeover: few txns, few IPs, VERY HIGH amounts vs normal baseline
                transaction_count = np.random.randint(5, 40)
                unique_ips = np.random.randint(1, 5)
                unique_devices = np.random.randint(1, 4)
                decline_rate = np.random.uniform(0.30, 0.80)
                current_amount = np.random.uniform(1000.0, 10000.0)
                average_amount = np.random.uniform(50.0, 400.0)  # way above normal baseline
            is_attack = 1

        amount_ratio = current_amount / average_amount if average_amount > 0 else 1.0
        hour_of_day = np.random.randint(0, 24)
        day_of_week = np.random.randint(1, 8)

        data.append({
            "transactionCount": transaction_count,
            "uniqueIps": unique_ips,
            "uniqueDevices": unique_devices,
            "declineRate": decline_rate,
            "currentAmount": current_amount,
            "averageAmount": average_amount,
            "amountRatio": amount_ratio,
            "hourOfDay": hour_of_day,
            "dayOfWeek": day_of_week,
            "is_attack": is_attack
        })
        
    df = pd.DataFrame(data)
    df.to_csv("ml/data/transactions.csv", index=False)
    attack_count = df["is_attack"].sum()
    print(f"Generated {num_samples} samples: {attack_count} attacks ({attack_count/num_samples*100:.0f}%), {num_samples-attack_count} normal")

if __name__ == "__main__":
    import os
    os.makedirs("ml/data", exist_ok=True)
    generate_synthetic_data()