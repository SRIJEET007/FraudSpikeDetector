package com.example.fraudDetector.model;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Entity
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table(name = "audit_logs")
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String transactionId;

    @Column(nullable = false)
    private String cardId;

    @Column(nullable = false)
    private String ipAddress;

    @Column(nullable = false)
    private String deviceId;

    @Column(nullable = false)
    private double amount;

    @Column(nullable = false)
    private LocalDateTime transactionTimestamp;

    private long transactionCount;
    private long uniqueIps;
    private long uniqueDevices;
    private double declineRate;
    private double averageAmount;
    private double amountRatio;
    private int hourOfDay;
    private int dayOfWeek;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Decision decision;

    @Column(nullable = false)
    private double mlScore;

    @Column(nullable = false)
    private boolean spike;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}
