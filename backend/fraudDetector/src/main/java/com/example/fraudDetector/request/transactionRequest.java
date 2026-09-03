package com.example.fraudDetector.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.time.LocalDateTime;

public record transactionRequest(
      @NotBlank String transactionId,
      @NotBlank  String cardId,
      @NotBlank  String ipAddress,
      @NotBlank  String deviceId,
      @NotNull boolean approved,
      @Positive double amount,
      @NotNull  LocalDateTime timeStamp
) {}
