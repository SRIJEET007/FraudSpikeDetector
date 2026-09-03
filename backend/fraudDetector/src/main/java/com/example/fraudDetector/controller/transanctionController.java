package com.example.fraudDetector.controller;

import com.example.fraudDetector.model.transactionDetails;
import com.example.fraudDetector.request.transactionRequest;
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
    public ResponseEntity<transactionDetails> ingestTxn(@Valid @RequestBody transactionRequest request)
    {
        transactionDetails details = service.processTransaction(request);
        return ResponseEntity.ok(details);
    }
}
