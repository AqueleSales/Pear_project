# 🔧 NOMAD SERVER — RESUMO TÉCNICO

## 📋 Checklist de Implementação

### Fase 1: API & Storage (Backend)
- [x] `nomad_api.py` — Flask API completa (11 endpoints)
  - [x] Host registration & lifecycle
  - [x] Dynamic tunnel updates
  - [x] Heartbeat monitoring
  - [x] World state management
  - [x] Whitelist system
  - [x] Audit logging
  - [x] Auto-cleanup de hosts inativos

- [x] `world_manager.py` — Persistência modular
  - [x] Compressão ZIP (9-level deflate)
  - [x] Suporte S3, Google Drive, Local
  - [x] SHA256 hashing
  - [x] Upload/download automático

### Fase 2: VPS Deployment
- [x] `setup_vps.sh` — Setup automático
  - [x] Usuário `nomad`
  - [x] Python + dependências
  - [x] Supervisord (auto-restart API)
  - [x] Nginx + reverse proxy
  - [x] Firewall UFW

- [x] `Dockerfile` + `docker-compose.yml`
  - [x] Container Python 3.11-slim
  - [x] Health check integrado
  - [x] Volumes para data persistence

- [x] `velocity.toml` — Configuração proxy
  - [x] Modern player forwarding
  - [x] Backend dinâmico

### Fase 3: Client (Launcher)
- [x] `launcher_desktop.py` — Tkinter UI
  - [x] Hardware analysis (CPU, RAM, disk)
  - [x] Tier classification (low/mid/high)
  - [x] Server startup/shutdown
  - [x] Ngrok + Cloudflare tunnel support
  - [x] Heartbeat thread (30s)
  - [x] Config persistence

### Fase 4: Integração
- [x] `NomadRouterPlugin.java` — Plugin Velocity
  - [x] Polling API (10s)
  - [x] Dynamic backend updates
  - [x] JSON parsing (sem libs)

- [x] `nomad_cli.py` — CLI admin
  - [x] Host management
  - [x] State queries
  - [x] Whitelist ops
  - [x] Audit log

- [x] `test_suite.py` — Testes completos
  - [x] API endpoints
  - [x] World compression
  - [x] Hardware detection
  - [x] Full lifecycle flow

## 🔌 API Endpoints

### HOST MANAGEMENT
```
POST   /api/host/register
       payload: { player_uuid, player_name, hardware_tier, version }
       response: { status, active_host }
       
POST   /api/host/update-tunnel
       payload: { player_uuid, public_ip, tunnel_port }
       response: { status, server_endpoint, velocity_will_reconnect_in_seconds }
       
POST   /api/host/heartbeat
       payload: { player_uuid, players_online, tps }
       response: { status }
       
POST   /api/host/shutdown
       payload: { player_uuid, save_file_hash, save_file_url }
       response: { status }
```

### STATE QUERIES
```
GET    /api/state/active-host
       response: { active, host: { name, endpoint, tier, uptime_minutes } }
       
GET    /api/state/world
       response: { exists, current_host, last_save, save_hash, save_url, players_online }
       
GET    /api/state/all-hosts       [AUTH REQUIRED]
       response: { total, hosts: [...] }
```

### WHITELIST
```
POST   /api/whitelist/add           [AUTH REQUIRED]
       payload: { player_uuid, player_name }
       response: { status }
       
GET    /api/whitelist/check/<uuid>
       response: { whitelisted, player_name }
```

### MONITORING
```
GET    /api/health
       response: { status, timestamp }
       
GET    /api/audit-log               [AUTH REQUIRED]
       response: { logs: [...] }
```

**[AUTH REQUIRED]** = Header `X-API-Key: <key>` obrigatório

## 🗂️ Database Schema

### hosts
```sql
id (PK)
player_uuid (UNIQUE)
player_name
public_ip              — IP externo do túnel
tunnel_port            — Porta do túnel
full_address           — ip:port
hardware_tier          — "low", "mid", "high"
last_heartbeat         — timestamp
status                 — "pending", "active", "offline"
version                — Versão do servidor (ex: 1.20.1)
```

### world_state
```sql
id (PK)
current_host_uuid      — UUID de quem hospeda
last_save_time         — timestamp
save_file_hash         — SHA256
save_file_url          — S3/GDrive/Local URL
total_players_online   — int
world_seed             — (para re-geração)
```

### player_whitelist
```sql
id (PK)
player_uuid (UNIQUE)
player_name
added_date             — timestamp
is_admin               — 0/1
```

### audit_log
```sql
id (PK)
timestamp
action                 — "REGISTER_HOST", "TUNNEL_UPDATE", etc
player_uuid
details                — JSON string
```

## 🚀 Fluxos Críticos

### START SERVER (Player inicia servidor)

```
Launcher.start_server()
  ├─ HardwareAnalyzer.get_tier()
  │   └─ Classifica como low/mid/high
  │
  ├─ API.register_host()
  │   ├─ INSERT hosts (status=pending)
  │   ├─ AUDIT "REGISTER_HOST"
  │   └─ Response: active_host (se houver)
  │
  ├─ download_world()  [se novo host]
  │   ├─ GET /api/state/world
  │   ├─ WorldManager.download(save_url)
  │   │   ├─ S3Backend.download() | GDriveBackend.download() | LocalBackend.download()
  │   │   └─ zipfile.extract()
  │   └─ Cleanup temp files
  │
  ├─ ServerManager.start_server()
  │   ├─ java -Xmx2G -jar server.jar
  │   ├─ Write eula.txt if needed
  │   └─ Monitor subprocess
  │
  ├─ TunnelManager.start()
  │   ├─ NgrokTunnel.start()
  │   │   ├─ ngrok authtoken
  │   │   ├─ ngrok tcp localhost:25565
  │   │   └─ Parse endpoint from ngrok API
  │   │
  │   └─ CloudflareTunnel.start()
  │       ├─ Write config file
  │       ├─ cloudflared tunnel run
  │       └─ Public endpoint: your-tunnel.trycloudflare.com
  │
  ├─ API.update_tunnel(public_ip, tunnel_port)
  │   ├─ UPDATE hosts (status=active)
  │   ├─ UPDATE world_state (current_host_uuid)
  │   └─ AUDIT "TUNNEL_UPDATE"
  │
  └─ Heartbeat loop (30s interval)
      ├─ API.send_heartbeat()
      │   ├─ UPDATE hosts (last_heartbeat)
      │   └─ UPDATE world_state (players_online)
      │
      └─ Velocity polling (10s)
          ├─ GET /api/state/active-host
          ├─ Parse endpoint
          └─ UnregisterServer() + RegisterServer() (dynamic update)
```

### STOP SERVER (Player sai)

```
Launcher.stop_server()
  ├─ ServerManager.stop_server()
  │   ├─ stdin.write("stop\n")
  │   ├─ Wait 10s for graceful shutdown
  │   └─ Kill -9 if timeout
  │
  ├─ TunnelManager.stop()
  │   └─ process.terminate()
  │
  ├─ WorldManager.upload_world()
  │   ├─ compress_world("world")
  │   │   ├─ zipfile.ZipFile(..., ZIP_DEFLATED, compresslevel=9)
  │   │   └─ Skip: session.lock, .pid, etc
  │   │
  │   ├─ calculate_hash(zip_path)
  │   │   └─ SHA256 de todo arquivo
  │   │
  │   └─ backend.upload(zip_path, remote_name)
  │       ├─ S3Backend: boto3.upload_file()
  │       ├─ GDriveBackend: drive.files().create()
  │       └─ LocalBackend: shutil.copy2()
  │
  └─ API.shutdown_host()
      ├─ UPDATE hosts (status=offline)
      ├─ UPDATE world_state (last_save_time, save_file_hash, save_file_url)
      ├─ AUDIT "HOST_SHUTDOWN"
      └─ Velocity perde backend (próximo polling)
```

### CONNECT TO SERVER (Player se conecta via Minecraft)

```
MinecraftClient.connect(velocity_ip:25565)
  ├─ Velocity.onConnect()
  │   ├─ GET /api/state/active-host
  │   ├─ RegisteredServer(backend_endpoint)
  │   └─ sendToServer(backend_server)
  │
  └─ Tunnel (ngrok/Cloudflare)
      └─ localhost:25565 (servidor local do host)
```

### AUTO-CLEANUP (Background task, 60s)

```
cleanup_inactive_hosts()
  ├─ SELECT * FROM hosts WHERE last_heartbeat < datetime('now', '-5 minutes') AND status='active'
  └─ UPDATE hosts SET status='offline'
```

## 🔐 Autenticação & Autorização

### API Key
- Enviada via `X-API-Key` header
- Verificada em todos `POST` e admin `GET`
- Stored em `$NOMAD_HOME/.env` (NEVER commit!)

### Decorator @require_api_key
```python
@require_api_key
def endpoint():
    # key validada
    ...
```

## 📊 Monitoramento & Alertas

### Métricas importantes
- **Hosts ativos**: SELECT COUNT(*) FROM hosts WHERE status='active'
- **Mundo online**: players_online from world_state
- **TPS**: tps from último heartbeat
- **Uptime**: last_heartbeat ago
- **Storage**: size de save_file_url

### Cron jobs
```bash
# Backup diário do banco
0 2 * * * cp /data/nomad_state.db /data/backups/nomad_state_$(date +%Y%m%d).db.backup

# Cleanup de backups >30 dias
0 3 * * 0 find /data/backups -mtime +30 -delete

# Health check (alert se down)
*/5 * * * * curl -f http://localhost:5000/api/health || send_alert()
```

## 🐛 Rate Limiting (Nginx)

```
/api/                     10 req/s (burst 20)
/storage/                 sem limite (downloads)
/api/state/               sem limite (queries)
```

## 📈 Performance Targets

| Métrica | Target |
|---------|--------|
| API latency | < 100ms |
| World compression | < 30s (1GB) |
| World upload | < 2m (1GB, S3) |
| Tunnel establishment | < 5s |
| Velocity backend update | < 10s (polling) |
| Heartbeat interval | 30s |
| Host timeout | 5 min (inatividade) |

## 🛡️ Deployment Checklist

- [ ] API key gerada e guardada
- [ ] HTTPS/SSL configurado (certbot)
- [ ] Firewall regras: 80, 443, 25565, 25575
- [ ] Backups automáticos habilitados
- [ ] Monitoring/alertas configurados
- [ ] Velocity rodando e conectado à API
- [ ] Plugin Velocity compilado e instalado
- [ ] World storage backend testado (S3/GDrive/Local)
- [ ] Launcher distribuído aos jogadores
- [ ] Teste full cycle: start → shutdown → start

## 🔄 Versioning

- **API version**: Via `config-version` em nomad_api.py
- **Protocol**: HTTP + JSON
- **Compatibility**: Launcher deveria checar `GET /api/health` antes de conectar

---

**Todas as implementações estão prontas para usar. Estender é fácil:**
- Novo backend storage? Estenda `StorageBackend`
- Novo serviço de tunelamento? Estenda `TunnelManager`
- Nova métrica? Adicione coluna em world_state/hosts
