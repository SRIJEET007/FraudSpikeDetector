package com.example.fraudDetector.controller;

import com.example.fraudDetector.model.EvaluationRun;
import com.example.fraudDetector.repository.EvaluationRunRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.File;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Slf4j
@RestController
@RequestMapping("/api/evaluation")
@CrossOrigin(origins = "*")
@RequiredArgsConstructor
public class EvaluationController {

    private final EvaluationRunRepository repository;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @GetMapping("/latest")
    public ResponseEntity<?> getLatestEvaluation() {
        Optional<EvaluationRun> latestOpt = repository.findTopByOrderByRunTimestampDesc();
        if (latestOpt.isPresent()) {
            return ResponseEntity.ok(latestOpt.get());
        }

        // Fallback: Read from ml/eval_results/metrics.json if DB record doesn't exist yet
        File file = new File("ml/eval_results/metrics.json");
        if (!file.exists()) {
            file = new File("../ml/eval_results/metrics.json");
        }
        if (file.exists()) {
            try {
                Map<String, Object> metrics = objectMapper.readValue(file, Map.class);
                return ResponseEntity.ok(metrics);
            } catch (Exception e) {
                log.error("Failed to read fallback metrics.json file", e);
            }
        }

        return ResponseEntity.notFound().build();
    }

    @GetMapping("/history")
    public ResponseEntity<List<EvaluationRun>> getEvaluationHistory() {
        List<EvaluationRun> history = repository.findAllByOrderByRunTimestampDesc();
        return ResponseEntity.ok(history);
    }

    @PostMapping("/record")
    public ResponseEntity<EvaluationRun> recordEvaluation(@RequestBody EvaluationRun run) {
        if (run.getRunTimestamp() == null) {
            run.setRunTimestamp(LocalDateTime.now());
        }
        EvaluationRun saved = repository.save(run);
        log.info("Recorded new evaluation run ID: {}", saved.getId());
        return ResponseEntity.ok(saved);
    }
}
