package com.example.fraudDetector.request;

import com.example.fraudDetector.model.transactionDetails;

/**
 * Dedicated DTO for the FastAPI /score endpoint.
 * Only contains the fields the ML model expects - no extra fields like cardId.
 */
public record mlScoreRequest(
        int transactionCount,
        int uniqueIps,
        int uniqueDevices,
        double declineRate,
        double currentAmount,
        double averageAmount,
        double amountRatio,
        int hourOfDay,
        int dayOfWeek
) {
    public static mlScoreRequest from(transactionDetails details) {
        return new mlScoreRequest(
                (int) details.transactionCount(),
                (int) details.uniqueIps(),
                (int) details.uniqueDevices(),
                details.declineRate(),
                details.currentAmount(),
                details.averageAmount(),
                details.amountRatio(),
                details.hourOfDay(),
                details.dayOfWeek()
        );
    }
}
