package com.example.fraudDetector.controller;

import com.example.fraudDetector.request.transactionRequest;
import com.example.fraudDetector.response.transactionResponse;
import com.example.fraudDetector.service.transactionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import com.example.fraudDetector.model.AuditLog;
import com.example.fraudDetector.repository.AuditLogRepository;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/v1/transactions")
@CrossOrigin(origins = "*")
@RequiredArgsConstructor
public class transactionController {
    private final transactionService service;
    private final AuditLogRepository auditLogRepository;

    @PostMapping
    public ResponseEntity<transactionResponse> ingestTxn(@Valid @RequestBody transactionRequest request) {
        transactionResponse response = service.processTransaction(request);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/recent")
    public ResponseEntity<List<AuditLog>> getRecentTransactions() {
        return ResponseEntity.ok(auditLogRepository.findTop50ByOrderByCreatedAtDesc());
    }
}
