package com.nomad.velocity;

import com.velocitypowered.api.event.proxy.ProxyInitializeEvent;
import com.velocitypowered.api.plugin.Plugin;
import com.velocitypowered.api.proxy.ProxyServer;
import com.velocitypowered.api.proxy.server.RegisteredServer;
import com.velocitypowered.api.proxy.server.ServerInfo;
import com.google.inject.Inject;
import java.net.InetSocketAddress;
import java.util.Timer;
import java.util.TimerTask;
import java.util.Optional;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import com.google.common.collect.ImmutableList;
import org.slf4j.Logger;

/**
 * NOMAD SERVER - VELOCITY PLUGIN
 * Conecta à API de roteamento e atualiza dynamicamente o backend server
 */

@Plugin(
    id = "nomad-router",
    name = "Nomad Router",
    version = "1.0",
    description = "Dynamic host routing for Nomad Server",
    authors = {"nomad-team"}
)
public class NomadRouterPlugin {

    private final ProxyServer proxy;
    private final Logger logger;
    private String apiUrl;
    private String apiKey;
    private String backendServerName = "nomad-backend";
    private Timer routeCheckTimer;
    private HttpClient httpClient;

    @Inject
    public NomadRouterPlugin(ProxyServer proxy, Logger logger) {
        this.proxy = proxy;
        this.logger = logger;
        this.httpClient = HttpClient.newHttpClient();
    }

    @com.velocitypowered.api.event.Subscribe
    public void onProxyInitialize(ProxyInitializeEvent event) {
        // Carrega config
        loadConfig();
        
        logger.info("========================================");
        logger.info("Nomad Router Plugin Initialized");
        logger.info("API URL: " + apiUrl);
        logger.info("Backend Server: " + backendServerName);
        logger.info("========================================");
        
        // Registra backend server dummy (será atualizado)
        registerBackendServer("127.0.0.1", 25565);
        
        // Inicia polling da API a cada 10 segundos
        routeCheckTimer = new Timer();
        routeCheckTimer.scheduleAtFixedRate(new UpdateRouteTask(), 0, 10000);
    }

    /**
     * Task que polling da API para atualizar rota
     */
    private class UpdateRouteTask extends TimerTask {
        @Override
        public void run() {
            try {
                updateRoute();
            } catch (Exception e) {
                logger.error("Error updating route", e);
            }
        }
    }

    /**
     * Faz request para API e atualiza backend server
     */
    private void updateRoute() throws Exception {
        String url = apiUrl + "/api/state/active-host";
        
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .header("X-API-Key", apiKey)
            .GET()
            .build();
        
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() != 200) {
            logger.warn("API returned status " + response.statusCode());
            return;
        }
        
        // Parse JSON response
        String body = response.body();
        
        if (body.contains("\"active\":false")) {
            logger.info("No active host available");
            // Desconecta backend
            unregisterBackendServer();
            return;
        }
        
        // Extrai endpoint do JSON
        // Resposta: {"active":true,"host":{"name":"Player1","endpoint":"123.45.67.89:25565",...}}
        
        String endpoint = extractJsonValue(body, "endpoint");
        if (endpoint == null || endpoint.isEmpty()) {
            logger.warn("No endpoint in response");
            return;
        }
        
        // Parse ip:port
        String[] parts = endpoint.split(":");
        if (parts.length < 2) {
            logger.warn("Invalid endpoint format: " + endpoint);
            return;
        }
        
        String ip = parts[0];
        int port = 25565;
        try {
            port = Integer.parseInt(parts[1]);
        } catch (NumberFormatException e) {
            logger.warn("Invalid port: " + parts[1]);
        }
        
        logger.info("Updating route: " + ip + ":" + port);
        updateBackendServer(ip, port);
    }

    /**
     * Atualiza ou registra backend server
     */
    private void updateBackendServer(String ip, int port) {
        Optional<RegisteredServer> existing = proxy.getServer(backendServerName);
        
        // Remove server antigo se existe
        if (existing.isPresent()) {
            proxy.unregisterServer(existing.get());
        }
        
        // Registra novo
        registerBackendServer(ip, port);
        
        logger.info("Backend server updated: " + ip + ":" + port);
    }

    /**
     * Registra um backend server
     */
    private void registerBackendServer(String ip, int port) {
        ServerInfo info = new ServerInfo(backendServerName, new InetSocketAddress(ip, port));
        RegisteredServer server = proxy.createRawRegisteredServer(info);
        proxy.registerServer(server);
    }

    /**
     * Remove backend server
     */
    private void unregisterBackendServer() {
        Optional<RegisteredServer> server = proxy.getServer(backendServerName);
        if (server.isPresent()) {
            proxy.unregisterServer(server.get());
            logger.info("Backend server unregistered");
        }
    }

    /**
     * Carrega configuração (de arquivo ou env)
     */
    private void loadConfig() {
        // Em produção: ler de velocity.toml ou env vars
        apiUrl = System.getenv("NOMAD_API_URL");
        apiKey = System.getenv("NOMAD_API_KEY");
        
        if (apiUrl == null) {
            apiUrl = "http://localhost:5000";
        }
        if (apiKey == null) {
            apiKey = "change-me-in-production";
        }
    }

    /**
     * Helper para extrair valor JSON simples
     */
    private String extractJsonValue(String json, String key) {
        String searchStr = "\"" + key + "\":\"";
        int startIdx = json.indexOf(searchStr);
        
        if (startIdx == -1) {
            return null;
        }
        
        int valueStart = startIdx + searchStr.length();
        int valueEnd = json.indexOf("\"", valueStart);
        
        if (valueEnd == -1) {
            return null;
        }
        
        return json.substring(valueStart, valueEnd);
    }
}

/**
 * ALTERNATIVE: Se usar library JSON (gson, jackson)
 * 
 * private void updateRoute() throws Exception {
 *     String url = apiUrl + "/api/state/active-host";
 *     HttpResponse<String> response = httpClient.send(
 *         HttpRequest.newBuilder()
 *             .uri(URI.create(url))
 *             .header("X-API-Key", apiKey)
 *             .GET()
 *             .build(),
 *         HttpResponse.BodyHandlers.ofString()
 *     );
 *     
 *     if (response.statusCode() != 200) return;
 *     
 *     JsonElement json = JsonParser.parseString(response.body());
 *     JsonObject obj = json.getAsJsonObject();
 *     
 *     if (!obj.get("active").getAsBoolean()) {
 *         logger.info("No active host");
 *         unregisterBackendServer();
 *         return;
 *     }
 *     
 *     String endpoint = obj.getAsJsonObject("host").get("endpoint").getAsString();
 *     String[] parts = endpoint.split(":");
 *     updateBackendServer(parts[0], Integer.parseInt(parts[1]));
 * }
 */
