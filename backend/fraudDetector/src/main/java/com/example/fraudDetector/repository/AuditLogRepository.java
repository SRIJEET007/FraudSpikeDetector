package com.example.fraudDetector.repository;

import com.example.fraudDetector.model.AuditLog;
import com.example.fraudDetector.model.Decision;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

    List<AuditLog> findByCardIdOrderByCreatedAtDesc(String cardId);
    List<AuditLog> findByDecision(Decision decision);
    List<AuditLog> findByCardIdAndDecision(String cardId, Decision decision);
    List<AuditLog> findByCreatedAtBetweenOrderByCreatedAtDesc(
            LocalDateTime start, LocalDateTime end);

    List<AuditLog> findByCardIdAndCreatedAtBetweenOrderByCreatedAtDesc(
            String cardId, LocalDateTime start, LocalDateTime end);

    List<AuditLog> findBySpikeTrue();

    List<AuditLog> findByCardIdAndSpikeTrue(String cardId);

    AuditLog findByTransactionId(String transactionId);
}
