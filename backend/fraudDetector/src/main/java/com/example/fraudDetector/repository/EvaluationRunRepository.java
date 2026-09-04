package com.example.fraudDetector.repository;

import com.example.fraudDetector.model.EvaluationRun;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface EvaluationRunRepository extends JpaRepository<EvaluationRun, Long> {
    Optional<EvaluationRun> findTopByOrderByRunTimestampDesc();
    List<EvaluationRun> findAllByOrderByRunTimestampDesc();
}
