package com.example.fraudDetector.service;

import com.example.fraudDetector.engine.featureEngine;
import com.example.fraudDetector.model.Decision;
import com.example.fraudDetector.model.transactionDetails;
import com.example.fraudDetector.request.transactionRequest;
import com.example.fraudDetector.response.transactionResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class transactionService
{
    private final slidingWindowService windowService;
    private final featureEngine engine;
    private final anomalyDetectorService anomaly;
    private final mlClientService mlService;
    public transactionResponse processTransaction(transactionRequest request)
    {

        //add the to the window.
        List<transactionRequest> window = windowService.slide(request);
        //extracting them features
        transactionDetails details = engine.extract(request,window);

        //spike detection using EWMA
        boolean isSpike = anomaly.evaluateSpike(details);

        //calling the ml service simultaneously along with z-scoring.
        double mlFraudScore = mlService.getFraudProbability(details);

        Decision decision;
        if (isSpike && mlFraudScore >= 0.7999) {
            decision = Decision.INSPECT;
            log.warn("[!!INSPECT!!] Card {} WARNING due to Layer 1 spike. ML score: {:.4f}", request.cardId(), mlFraudScore);
        } else if (mlFraudScore >= 0.4777) {
            decision = Decision.SUSPICIOUS;
            log.info("[!SUSPICIOUS!] Card {} look for any mischief. ML score: {:.4f}", request.cardId(), mlFraudScore);
        } else {
            decision = Decision.APPROVE;
            log.info("[APPROVE] Card {} transaction allowed.", request.cardId());
        }

        details.summary();

        return new transactionResponse(decision,mlFraudScore,isSpike,details);
    }
}
