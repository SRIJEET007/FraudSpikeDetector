package com.example.fraudDetector.service;

import com.example.fraudDetector.model.cardBaseLine;
import com.example.fraudDetector.model.transactionDetails;
import org.springframework.stereotype.Service;

import java.util.concurrent.ConcurrentHashMap;

@Service
public class anomalyDetectorService {

    //THIS SERVICE DETECTS ANY SUDDEN SPIKE IN THE FREQUENCY OF TRANSACTIONS. USING EWMA SCORE.
    private static final double Z_SCORE_THRESHOLD = 2.0;
    private final ConcurrentHashMap<String, cardBaseLine> baselines = new ConcurrentHashMap<>();

    public boolean evaluateSpike(transactionDetails details)
    {
        cardBaseLine baseline = baselines.computeIfAbsent(details.cardId(), x -> new cardBaseLine());
        double currentValue = details.transactionCount();

        //calcualting z score
        double mean = baseline.getEwmaMean();
        double stdDev = baseline.getStandardDeviation();
        double zScore = (currentValue - mean) / stdDev;

        boolean isSuspicious = zScore > Z_SCORE_THRESHOLD;
        baseline.update(currentValue,isSuspicious);

        if (isSuspicious) {
            System.err.println("\n [SPIKE DETECTED] Layer 1 Alert!");
            System.err.printf("Card: %s | Current Count: %.1f | Normal Mean: %.1f | Z-Score: %.2f\n",
                    details.cardId(), currentValue, mean, zScore);
        } else {
            System.out.printf(" [Normal] Card: %s | Count: %.1f | Mean: %.1f | Z-Score: %.2f\n",
                    details.cardId(), currentValue, mean, zScore);
        }
        return isSuspicious;
    }
}
