package com.datadog.repro;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

@SpringBootApplication
@RestController
public class IdentityProxyApplication {

    private static final List<byte[]> RESPONSE_CACHE = Collections.synchronizedList(new ArrayList<>());
    private static final AtomicBoolean CACHE_WARMING = new AtomicBoolean(false);

    private static final Path PHASE_FILE = Path.of(
            System.getenv().getOrDefault("CASCADE_STATE_DIR", "/cascade-state"),
            "identity-proxy-phase.json");

    public static void main(String[] args) {
        Thread cacheRefresh = new Thread(() -> {
            Runtime rt = Runtime.getRuntime();
            while (true) {
                try {
                    pollCascadeState();
                    if (CACHE_WARMING.get()) {
                        long used = rt.totalMemory() - rt.freeMemory();
                        if (used < rt.maxMemory() * 0.82) {
                            RESPONSE_CACHE.add(new byte[1024 * 1024]);
                        }
                    } else if (!RESPONSE_CACHE.isEmpty()) {
                        RESPONSE_CACHE.clear();
                        System.gc();
                    }
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    break;
                }
            }
        }, "cache-refresh");
        cacheRefresh.setDaemon(true);
        cacheRefresh.start();
        SpringApplication.run(IdentityProxyApplication.class, args);
    }

    private static void pollCascadeState() {
        try {
            if (!Files.exists(PHASE_FILE)) return;
            String content = Files.readString(PHASE_FILE);
            if (content.contains("\"sustained\"") || content.contains("\"ramp\"")) {
                CACHE_WARMING.set(true);
            } else if (content.contains("\"recovering\"") || content.contains("\"normal\"")) {
                CACHE_WARMING.set(false);
            }
        } catch (IOException ignored) {}
    }

    private static double fillRatio() {
        Runtime rt = Runtime.getRuntime();
        long used = rt.totalMemory() - rt.freeMemory();
        return (double) used / (double) rt.maxMemory();
    }

    @RequestMapping("/identity-v1/**")
    public Map<String, Object> proxy() throws InterruptedException {
        double fill = fillRatio();
        long extraMs = CACHE_WARMING.get() ? (long) (Math.max(0.0, fill - 0.40) * 900) : 0L;
        if (extraMs > 0) {
            Thread.sleep(extraMs);
        }
        if (CACHE_WARMING.get() && fill > 0.78 && Math.random() < 0.20) {
            throw new RuntimeException("upstream timeout: identity-v1 service unavailable");
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("ok", true);
        body.put("cacheSizeMB", RESPONSE_CACHE.size());
        return body;
    }

    @GetMapping("/admin/config")
    public Map<String, Object> updateConfig(@RequestParam(defaultValue = "") String cacheMode) {
        if ("aggressive".equals(cacheMode)) CACHE_WARMING.set(true);
        else if ("standard".equals(cacheMode)) CACHE_WARMING.set(false);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("cacheMode", CACHE_WARMING.get() ? "aggressive" : "standard");
        body.put("cacheSizeMB", RESPONSE_CACHE.size());
        body.put("heapFillPct", Math.round(fillRatio() * 100));
        return body;
    }
}
