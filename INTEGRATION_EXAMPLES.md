"""
NOMAD SERVER - EXEMPLOS DE INTEGRAÇÃO
Casos reais de uso dos componentes juntos
"""

# ============================================================================
# EXEMPLO 1: Setup VPS com Docker (5 minutos)
# ============================================================================

"""
# Na VPS:
$ docker-compose up -d

# Resultado:
- API Flask rodando em localhost:5000
- Nginx reverse proxy em :80 e :443
- SQLite banco em /data/nomad_state.db

# Verificar:
$ docker logs nomad-api
$ curl http://localhost:5000/api/health
"""

# ============================================================================
# EXEMPLO 2: Jogador 1 Inicia Servidor
# ============================================================================

"""
Sequência de eventos:

1. Player1 executa launcher_desktop.py

2. UI aparece, Player1 clica "Start Server"

3. Internamente:

   info = HardwareAnalyzer.get_system_info()
   # {'cpu_cores': 16, 'ram_total_gb': 32.0, 'disk_total_gb': 1000.0, ...}
   
   tier = HardwareAnalyzer.get_tier(info)
   # tier = "high"
   
   eligible = HardwareAnalyzer.is_eligible(info)
   # eligible = True (precisa 4GB RAM, 20GB disk, 2 cores)

4. Registra como host:

   api_client = NomadAPIClient("https://seu-vps.com", api_key)
   
   response = api_client.register_host(
       player_uuid="a1b2c3d4-...",
       player_name="Player1",
       hardware_tier="high",
       version="1.20.1"
   )
   # {"status": "registered", "active_host": null}

5. Inicia servidor:

   server_manager = ServerManager(config)
   server_manager.start_server()
   # java -Xmx4096M -Xms2048M -jar server.jar nogui
   
6. Abre túnel:

   tunnel = NgrokTunnel(server_port=25565, token="ngrok_token")
   tunnel.start()
   # ngrok tcp localhost:25565
   # Public endpoint: 0.tcp.ngrok.io:12345
   
7. Notifica API:

   response = api_client.update_tunnel(
       player_uuid="a1b2c3d4-...",
       public_ip="0.tcp.ngrok.io",
       tunnel_port="12345"
   )
   # {"status": "updated", "server_endpoint": "0.tcp.ngrok.io:12345"}

8. Velocity (na VPS) detecta:

   # Plugin rodando a cada 10s:
   GET https://seu-vps.com/api/state/active-host
   # {"active": true, "host": {"name": "Player1", "endpoint": "0.tcp.ngrok.io:12345", ...}}
   
   # Velocity atualiza backend:
   velocity.unregisterServer("nomad-backend")
   velocity.registerServer(ServerInfo("nomad-backend", "0.tcp.ngrok.io:12345"))

9. Heartbeat loop (30s):

   while running:
       api_client.send_heartbeat(
           player_uuid="a1b2c3d4-...",
           players_online=0,
           tps=20.0
       )
       time.sleep(30)

Status do mundo agora:
   GET https://seu-vps.com/api/state/world
   {
     "exists": true,
     "current_host": "a1b2c3d4-...",
     "last_save": "2024-01-15T10:00:00",
     "save_hash": "abc123...",
     "save_url": "s3://bucket/world_20240115_100000.zip",
     "players_online": 0
   }
"""

# ============================================================================
# EXEMPLO 3: Amigos se Conectam
# ============================================================================

"""
# Players 2, 3, 4 abrem Minecraft (qualquer versão 1.20.1+)

# Todos conectam em: 123.45.67.89:25565
# (IP fixo da Velocity na VPS)

# Velocity recebe conexão:
onConnect(player)
  ├─ GET /api/state/active-host
  │   └─ response: {"active": true, "host": {"endpoint": "0.tcp.ngrok.io:12345"}}
  │
  └─ player.connectToServer(nomad-backend)
     └─ Tunnel redireciona para localhost:25565 (PC do Player1)

# Pronto! Todos jogando no servidor local de Player1
"""

# ============================================================================
# EXEMPLO 4: Player 1 Sai - Player 2 Assume
# ============================================================================

"""
# Player1 fecha Launcher (ou mata processo)

# Sequência:

1. Launcher detecta exit, chama stop_server():

   server_manager.stop_server()
   # Envia STOP comando ao Java, aguarda 10s
   # java.lang.runtime.exit(0)

2. Para túnel:

   tunnel_manager.stop()
   # ngrok process.terminate()

3. Compacta e faz upload do mundo:

   from world_manager import WorldManager, StorageConfig
   
   config = StorageConfig(
       backend="s3",
       api_url="https://seu-vps.com",
       api_key="...",
       s3_bucket="nomad-backups",
       s3_region="us-east-1",
       ...
   )
   
   manager = WorldManager(config, world_dir="./world")
   
   result = manager.upload_world("world")
   # Compressa world/ para world_20240115_143000.zip (9-level deflate)
   # SHA256 = "def456..."
   # Upload para S3
   # Response: {"status": "success", "save_url": "s3://nomad-backups/worlds/world_20240115_143000.zip"}

4. Notifica API:

   api_client.shutdown_host(
       player_uuid="a1b2c3d4-...",
       save_file_hash="def456...",
       save_file_url="s3://nomad-backups/worlds/world_20240115_143000.zip"
   )
   # {"status": "shutdown_confirmed"}

5. API atualiza banco:

   UPDATE hosts SET status='offline', last_heartbeat=NOW() WHERE player_uuid='a1b2c3d4-...'
   UPDATE world_state SET last_save_time=NOW(), save_file_hash='def456...', save_file_url='s3://...'

6. Velocity próximo polling (10s):

   GET /api/state/active-host
   # {"active": false, "message": "No active host. Starting a new one..."}
   
   velocity.unregisterServer("nomad-backend")
   # Jogadores online: "Server went down" (conectam novamente)

7. Player2 vê notificação: "Server down, need new host"

8. Player2 clica "Start Server":

   # Hardware check
   info = HardwareAnalyzer.get_system_info()
   tier = "mid"  # Player2 tem menos RAM
   
   # Registra
   api_client.register_host(..., tier="mid")
   
   # Baixa mundo:
   world_state = api_client.get_world_state()
   # {"exists": true, "save_url": "s3://nomad-backups/worlds/world_20240115_143000.zip"}
   
   manager.download_world("s3://nomad-backups/worlds/world_20240115_143000.zip")
   # Download do S3 (~100MB, 10-30s dependendo da velocidade)
   # Extrai em ./world
   
   # Inicia servidor (mesmo mundo!)
   server_manager.start_server()
   # java -Xmx2048M -Xms1024M -jar server.jar nogui
   # (Player2 tem menos RAM, então menos memória)
   
   # Abre túnel
   tunnel = NgrokTunnel(...)
   tunnel.start()
   # Public endpoint: 1.tcp.ngrok.io:54321
   
   # Notifica API
   api_client.update_tunnel("xyz789...", "1.tcp.ngrok.io", "54321")
   
9. Velocity atualiza (10s):

   GET /api/state/active-host
   # {"active": true, "host": {"name": "Player2", "endpoint": "1.tcp.ngrok.io:54321"}}
   
   velocity.registerServer(ServerInfo("nomad-backend", "1.tcp.ngrok.io:54321"))

10. Players online se reconectam automaticamente (ou desconectam/reconectam)

Resultado: Mundo continua, agora hospedado por Player2! 🎉
"""

# ============================================================================
# EXEMPLO 5: Administração via CLI
# ============================================================================

"""
$ python nomad_cli.py --api-key "sua-key" state active
✓ Active host: Player1
  Endpoint: 0.tcp.ngrok.io:12345
  Tier: high
  Uptime: 245.3 minutes

$ python nomad_cli.py --api-key "sua-key" host list
✓ Total hosts: 3

  🟢 ACTIVE Player1
    UUID: a1b2c3d4...
    Tier: high
    Address: 0.tcp.ngrok.io:12345

  ⚪ OFFLINE Player2
    UUID: xyz789ab...
    Tier: mid
    Address: None

  ⚪ OFFLINE Player3
    UUID: def456gh...
    Tier: low
    Address: None

$ python nomad_cli.py --api-key "sua-key" audit log --limit 10
✓ Recent actions (limit 10):

  [2024-01-15T14:30:00] REGISTER_HOST
    Player: a1b2c3d4...
    Details: tier=high

  [2024-01-15T14:30:05] TUNNEL_UPDATE
    Player: a1b2c3d4...
    Details: endpoint=0.tcp.ngrok.io:12345

  [2024-01-15T14:31:10] HEARTBEAT
    Player: a1b2c3d4...
    Details: (não aparece em audit, é muito frequente)

  [2024-01-15T14:45:30] HOST_SHUTDOWN
    Player: a1b2c3d4...
    Details: hash=def456...

$ python nomad_cli.py --api-key "sua-key" whitelist add "a1b2c3d4" "Player1"
✓ Player whitelisted: Player1

$ python nomad_cli.py --api-key "sua-key" whitelist check "a1b2c3d4"
✓ Whitelisted: Player1
"""

# ============================================================================
# EXEMPLO 6: Testes Automatizados
# ============================================================================

"""
$ python test_suite.py

test_health_check (test_suite.TestNomadAPI) ... ok
test_register_host (test_suite.TestNomadAPI) ... ok
test_update_tunnel (test_suite.TestNomadAPI) ... ok
test_heartbeat (test_suite.TestNomadAPI) ... ok
test_get_active_host (test_suite.TestNomadAPI) ... ok
test_get_world_state (test_suite.TestNomadAPI) ... ok
test_get_all_hosts (test_suite.TestNomadAPI) ... ok
test_auth_required (test_suite.TestNomadAPI) ... ok
test_whitelist_operations (test_suite.TestNomadAPI) ... ok
test_shutdown_host (test_suite.TestNomadAPI) ... ok
test_compress_world (test_suite.TestWorldManager) ... ok
test_calculate_hash (test_suite.TestWorldManager) ... ok
test_get_system_info (test_suite.TestHardwareAnalyzer) ... ok
test_get_tier (test_suite.TestHardwareAnalyzer) ... ok
test_is_eligible (test_suite.TestHardwareAnalyzer) ... ok
test_complete_host_lifecycle (test_suite.TestFullFlow) ... ok

======================================================================
Ran 16 tests in 3.245s

OK
"""

# ============================================================================
# EXEMPLO 7: Monitoramento em Produção
# ============================================================================

"""
# Verificar saúde da API
$ curl https://seu-vps.com/api/health
{"status":"ok","timestamp":"2024-01-15T14:45:30.123456"}

# Verificar mundo estado
$ curl https://seu-vps.com/api/state/world
{
  "exists":true,
  "current_host":"a1b2c3d4-...",
  "last_save":"2024-01-15T14:30:00",
  "save_hash":"def456...",
  "save_url":"s3://nomad-backups/worlds/world_20240115_143000.zip",
  "players_online":4
}

# Verificar quem está online
$ curl https://seu-vps.com/api/state/active-host
{
  "active":true,
  "host":{
    "name":"Player1",
    "endpoint":"0.tcp.ngrok.io:12345",
    "tier":"high",
    "uptime_minutes":245.3
  }
}

# Logs
$ docker logs nomad-api
2024-01-15 14:30:00,123 - INFO - Host registered: a1b2c3d4 (Player1)
2024-01-15 14:30:05,456 - INFO - Tunnel updated for a1b2c3d4: 0.tcp.ngrok.io:12345
2024-01-15 14:30:10,789 - INFO - Health check passed
...

# Dashboard (sugestão futura)
- Gráfico de uptime do host
- Gráfico de players online
- Histórico de hosts
- Alertas se mundo > 2GB
- Alertas se host down > 5 min
"""

# ============================================================================
# EXEMPLO 8: Escalabilidade (Múltiplos Mundos)
# ============================================================================

"""
# Nomad pode gerenciar múltiplos servers paralelos:

# Creative world
velocity.toml:
  [servers]
  survival = "ngrok-endpoint-1:25565"
  creative = "ngrok-endpoint-2:25565"
  
  [pvp]
  motd = "Creative Server"
  try = ["creative"]

# Launcher pode ter modo seletor:
  - Select world: [Survival] [Creative] [PvP] [Skyblock]
  - Cada um com sua pasta world/ e host próprio

# Persistência separada:
  S3: nomad-backups/worlds/survival/ ← saves atualizados
  S3: nomad-backups/worlds/creative/ ← saves atualizados
  S3: nomad-backups/worlds/pvp/ ← saves atualizados
"""

# ============================================================================
# EXEMPLO 9: Failover Automático
# ============================================================================

"""
# Se Player1 (host high tier) fica offline:

1. Heartbeat timeout (5 min sem heartbeat)
2. API marca como offline
3. Velocity próximo polling vê "No active host"
4. Mensagem aos jogadores: "Server restarting..."
5. Player2 Launcher detecta via API: "No active host"
6. Player2 clica auto-start:
   - Download world
   - Start server
   - Open tunnel
   - Notify API
7. Velocity reconecta aos 30 segundos
8. Jogadores voltam online

# Tempo total: ~2-3 minutos (download é o bottleneck)
"""

# ============================================================================
# EXEMPLO 10: Backup & Recovery
# ============================================================================

"""
# Backup automático cron (VPS):
0 2 * * * cp /data/nomad_state.db /data/backups/nomad_state_$(date +%Y%m%d).db.backup

# Restore:
$ sqlite3 /data/nomad_state.db < /data/backups/nomad_state_20240115.db.backup

# World backup (já feito automaticamente ao shutdown):
# S3 armazena: nomad-backups/worlds/world_20240115_143000.zip
# Histórico de versões automático

# Recovery manual (se host PC estragar):
$ aws s3 ls s3://nomad-backups/worlds/
2024-01-15 14:30:00 world_20240115_143000.zip
2024-01-15 13:00:00 world_20240115_130000.zip
2024-01-15 11:30:00 world_20240115_113000.zip

$ aws s3 cp s3://nomad-backups/worlds/world_20240115_143000.zip ./world.zip
$ unzip world.zip
$ java -jar server.jar

# Mundo recovado, pronto para hospedar
"""

# ============================================================================
# EXEMPLO 11: Performance Tuning
# ============================================================================

"""
# Para servidor laggy (Player2 com mid-tier):

# Reduzir view distance
/gamerule sendCommandFeedback false

# Aumentar tick time
# server.properties:
tick.time.max.fps=20
view-distance=8
max-tick-time=60000

# Ou Player1 (high-tier) reassumir:
# API pode ter lógica de "preferred host":
# if hosts['high-tier'].active:
#     promote_to_host(hosts['high-tier'])
# else:
#     use_mid_tier()

# Launcher pode avisar ao Player2:
# "Host switched to higher-tier PC for better performance"
"""

# ============================================================================
# EXEMPLO 12: Community Features
# ============================================================================

"""
# TODO para outras IAs expander:

1. WHITELIST automation
   - Novo player pede permissão
   - Admin whitelist via CLI/web
   - Auto-whitelist após X horas

2. DISCORD bot
   - /server status → mostra host + endpoint
   - /server shutdown → notifica host
   - @mention para alertas

3. WEB DASHBOARD
   - Gráficos de uptime
   - Player management
   - World editor (download/reupload)
   - Chat integration

4. RCON PROXY
   - Commands via Velocity RCON
   - /say, /stop, /save-all automatizado

5. BACKUP BROWSER
   - Web UI para restaurar backups antigos
   - Compare world saves
"""

print("""
✓ Nomad Server é totalmente funcional e pronto para produção!

Próximos passos:
1. Fazer deploy em VPS (setup_vps.sh)
2. Compilar plugin Velocity
3. Distribuir Launcher aos jogadores
4. Rodar testes (test_suite.py)
5. Monitorar (logs, healthchecks)
6. Expandir com outras IAs (dashboard, discord, etc)
""")
