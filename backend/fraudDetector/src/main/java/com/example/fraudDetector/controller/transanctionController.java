package com.example.fraudDetector.controller;

import com.example.fraudDetector.model.transactionDetails;
import com.example.fraudDetector.request.transactionRequest;
import com.example.fraudDetector.response.transactionResponse;
import com.example.fraudDetector.service.transactionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/transactions")
@RequiredArgsConstructor
public class transanctionController {
    private final transactionService service;

    @PostMapping
    public ResponseEntity<transactionResponse> ingestTxn(@Valid @RequestBody transactionRequest request)
    {
        transactionResponse response= service.processTransaction(request);
        return ResponseEntity.ok(response);
    }
}
