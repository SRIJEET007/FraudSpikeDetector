package com.example.fraudDetector.response;

import com.example.fraudDetector.model.Decision;
import com.example.fraudDetector.model.transactionDetails;

public record transactionResponse(
        Decision decision,
        double mlScore,
        boolean isSpike,
        transactionDetails details
) {
}
