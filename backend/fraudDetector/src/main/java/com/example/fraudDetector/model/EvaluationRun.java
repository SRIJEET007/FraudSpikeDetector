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
@Table(name = "evaluation_runs")
public class EvaluationRun {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private LocalDateTime runTimestamp;

    private double precisionScore;
    private double recallScore;
    private double f1Score;
    private double falsePositiveRate;
    private double thresholdUsed;
    private double netValue;
    private double costPerTxn;

    private int totalTransactions;
    private int actualFraud;
    private int actualLegit;

    private int truePositives;
    private int falsePositives;
    private int trueNegatives;
    private int falseNegatives;

    private String evaluationMode;

    @Column(columnDefinition = "TEXT")
    private String confusionMatrix;

    @Column(columnDefinition = "TEXT")
    private String thresholdSweep;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (this.runTimestamp == null) {
            this.runTimestamp = LocalDateTime.now();
        }
        this.createdAt = LocalDateTime.now();
    }
}
