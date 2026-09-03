package com.example.fraudDetector.service;

import com.example.fraudDetector.request.transactionRequest;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedDeque;

@Service
public class slidingWindowService {
    //THE WINDOW SIZE OF THE TRANSACTION RECORDS BEING CHECKED.
    //currently kept at 60s, will be updated, once migrated to redis instead of hashmap
    public static final long WINDOW_SECOND = 60;

    //TODO -- upgrade to redis from local state ;-;
    public ConcurrentHashMap<String, Deque<transactionRequest>> cardWindow = new ConcurrentHashMap<>();

    public List<transactionRequest> slide(transactionRequest txn)
    {
        cardWindow.putIfAbsent(txn.cardId(), new ConcurrentLinkedDeque<>());
        Deque<transactionRequest> queue=cardWindow.get(txn.cardId());

        synchronized (queue)
        {
            queue.addLast(txn);
            LocalDateTime cutoff = txn.timeStamp().minusSeconds(WINDOW_SECOND);
            while (!queue.isEmpty() && queue.peekFirst().timeStamp().isBefore(cutoff))
            {
                queue.pollFirst();
            }
        }

        return new ArrayList<>(queue);
    }
}
