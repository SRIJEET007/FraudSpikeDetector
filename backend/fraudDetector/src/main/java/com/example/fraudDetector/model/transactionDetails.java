package com.example.fraudDetector.model;

public record transactionDetails(
        String cardId,
        long transactionCount,
        long uniqueIps,
        long uniqueDevices,
        double declineRate,
        double currentAmount,
        double averageAmount,
        double amountRatio,
        int hourOfDay,
        int dayOfWeek
) {
    public void summary()
    {
        System.out.println("\n----------------------------------------");
        System.out.println("CARD: " + cardId);
        System.out.println("Transactions: " + transactionCount);
        System.out.println("Unique IPs: " + uniqueIps);
        System.out.println("Unique devices: " + uniqueDevices);
        System.out.printf("Decline rate: %.0f%%\n", declineRate * 100);
        System.out.printf("Current Amount: $%.2f | Avg Amount: $%.2f (Ratio: %.2f)\n", currentAmount, averageAmount, amountRatio);
        System.out.println("Time: Hour " + hourOfDay + " | Day " + dayOfWeek);
        System.out.println("----------------------------------------\n");
    }
}
