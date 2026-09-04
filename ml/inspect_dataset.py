import pandas as pd

cols = ['TransactionID','isFraud','TransactionDT','TransactionAmt','ProductCD',
        'card1','card2','card3','card4','card5','card6',
        'addr1','addr2','P_emaildomain','C1','C2','C13','C14','D1','D15']
df = pd.read_csv('ml/data/train_transaction.csv', usecols=cols)

print("Shape:", df.shape)
print()

print("isFraud distribution:")
print(df['isFraud'].value_counts())
fraud_rate = df['isFraud'].mean() * 100
print("Fraud rate: {:.2f}%".format(fraud_rate))
print()

print("TransactionDT range:", df['TransactionDT'].min(), "-", df['TransactionDT'].max())
print()

print("TransactionAmt stats:")
print(df['TransactionAmt'].describe())
print()

print("card1 nunique:", df['card1'].nunique())
print("ProductCD values:", df['ProductCD'].value_counts().to_dict())
print()

# 80/20 time split
cutoff = df['TransactionDT'].quantile(0.8)
print("80th percentile TransactionDT:", cutoff)
train_part = df[df['TransactionDT'] <= cutoff]
test_part = df[df['TransactionDT'] > cutoff]
train_fraud = train_part['isFraud'].mean() * 100
test_fraud = test_part['isFraud'].mean() * 100
print("Train (first 80%): {} rows, fraud rate: {:.2f}%".format(len(train_part), train_fraud))
print("Test  (last  20%): {} rows, fraud rate: {:.2f}%".format(len(test_part), test_fraud))

# Check C1, C2, C13 ranges (count-like columns that could map to our features)
print()
print("C1 (possible txn count proxy):")
print(df['C1'].describe())
print()
print("C13 stats:")
print(df['C13'].describe())
print()
print("D1 stats (days since last txn):")
print(df['D1'].describe())
