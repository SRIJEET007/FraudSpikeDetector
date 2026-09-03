package com.example.fraudDetector.engine;

import com.example.fraudDetector.model.transactionDetails;
import com.example.fraudDetector.request.transactionRequest;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

@Component
public class featureEngine {

    public transactionDetails extract(transactionRequest currentTxn, List<transactionRequest> window)
    {
        int count = window.size();
        long uniqueIps = window.stream()
                .map(transactionRequest::ipAddress)
                .distinct()
                .count();

        long uniqueDevices = window.stream()
                .map(transactionRequest::deviceId)
                .distinct()
                .count();

        long declinedCount = window.stream()
                .filter(t -> !t.approved())
                .count();

        double declineRate = count > 0 ? (double) declinedCount / count : 0.0;

        double averageAmount = window.stream()
                .mapToDouble(transactionRequest::amount)
                .average()
                .orElse(0.0);

        double amountRatio = averageAmount > 0 ? currentTxn.amount() / averageAmount : 1.0;

        LocalDateTime timestamp = currentTxn.timeStamp();
        int hourOfDay = timestamp.getHour();
        int dayOfWeek = timestamp.getDayOfWeek().getValue(); // 1 = Monday, 7 = Sunday

        return new transactionDetails(
                currentTxn.cardId(),
                count,
                uniqueIps,
                uniqueDevices,
                declineRate,
                currentTxn.amount(),
                averageAmount,
                amountRatio,
                hourOfDay,
                dayOfWeek
        );
    }
}
