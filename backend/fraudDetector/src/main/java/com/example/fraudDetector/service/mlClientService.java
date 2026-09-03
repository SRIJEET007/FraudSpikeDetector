package com.example.fraudDetector.service;

import com.example.fraudDetector.model.transactionDetails;
import com.example.fraudDetector.request.mlScoreRequest;
import com.example.fraudDetector.response.mlResponse;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class mlClientService {

    private final RestTemplate restTemplate;
    private static final String ML_URL = "http://localhost:5000/score";

    mlClientService() {
        this.restTemplate = new RestTemplate();
    }

    public double getFraudProbability(transactionDetails details) {
        try {
            // Build a clean request with only the fields FastAPI expects
            mlScoreRequest payload = mlScoreRequest.from(details);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<mlScoreRequest> entity = new HttpEntity<>(payload, headers);
            ResponseEntity<mlResponse> response = restTemplate.postForEntity(ML_URL, entity, mlResponse.class);

            return response.getBody() != null ? response.getBody().fraudProbability() : 0.0;
        } catch (Exception e) {
            System.err.println("[ALERT] ML service error: " + e.getMessage());
            return 0.0;
        }
    }
}
