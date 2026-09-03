package com.example.fraudDetector.service;

import com.example.fraudDetector.engine.featureEngine;
import com.example.fraudDetector.model.transactionDetails;
import com.example.fraudDetector.request.transactionRequest;
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
    public transactionDetails processTransaction(transactionRequest request)
    {

        //add the to the window.
        List<transactionRequest> window = windowService.slide(request);
        //extracting them features
        transactionDetails details = engine.extract(request,window);
        details.summary();

        //detection using EWMA
        boolean isSuspicious = anomaly.evaluateSpike(details);

        if (isSuspicious)
        {
            log.warn("Transaction stream for {} flagged by Layer 1 detector.", request.cardId());
        }

        return details;
    }
}
