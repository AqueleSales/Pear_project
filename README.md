# 🎮 NOMAD SERVER - Infraestrutura de Minecraft Dinâmica

## 📋 O que é

Nomad Server é uma arquitetura descentralizada para Minecraft que permite que **qualquer jogador com hardware decente hospede o servidor**, enquanto a nuvem gerencia apenas o roteamento. Não paga pelos servidores 24/7.

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    NUVEM (VPS Grátis)                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Velocity (Proxy)  +  API Flask  +  Nginx            │   │
│  │  • IP fixo 123.45.67.89                              │   │
│  │  • Redireciona para host atual                        │   │
│  │  • Gerencia estado do mundo                          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
              ↑              ↑              ↑
        (HTTP API)      (Heartbeat)    (Túnel dinâmico)
              │              │              │
┌─────────────┴──────────────┴──────────────┴───────────────────┐
│                   HOSTS (PCs de Jogadores)                    │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  Host 1 (Player1): Launcher + Servidor Java + Túnel   │   │
│  │  - ngrok/Cloudflare expõe porta 25565                 │   │
│  │  - Envia IP dinâmico para API                          │   │
│  │  - Jogadores conectam via Velocity (proxy)            │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  Host 2 (Player2): STANDBY (pronto para assumir)      │   │
│  └────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start (Produção)

### 1. Preparar VPS Nuvem

```bash
# SSH na VPS (Replit, Oracle Free Tier, Heroku, etc)
# Rodar setup_vps.sh (ou docker-compose)

# Opção A: Script automático
bash setup_vps.sh

# Opção B: Docker (recomendado)
docker-compose up -d
```

**Guarde a API_KEY após setup!**

### 2. Configurar Velocity (na nuvem)

```bash
# Download
wget https://api.papermc.io/v2/projects/velocity/versions/3.3.0-SNAPSHOT/builds/latest/downloads/velocity-3.3.0-SNAPSHOT-all.jar

# Copiar velocity.toml
cp velocity.toml /opt/velocity/

# Rodar
java -jar velocity.jar
```

### 3. Launcher nos PCs (Jogadores)

```bash
# Instalação (Python 3.8+)
pip install -r requirements.txt

# Configurar (primeiro uso)
python launcher_desktop.py

# UI vai pedir:
# - Nome do jogador
# - API URL (ex: https://seu-vps.com)
# - API Key
# - ngrok/Cloudflare token (se usar tunelamento pago)

# Depois: clicar "Start Server" 
# Launcher faz tudo: baixa mundo, inicia Java, abre túnel
```

## 📦 Arquivos Inclusos

| Arquivo | Função |
|---------|--------|
| `nomad_api.py` | API Flask — gerencia estado, hosts, mundo |
| `world_manager.py` | Persistência — upload/download de mapas (S3/GDrive/Local) |
| `launcher_desktop.py` | Interface Tkinter — para jogadores iniciarem servidor |
| `NomadRouterPlugin.java` | Plugin Velocity — atualiza rota dinamicamente |
| `setup_vps.sh` | Script automático de setup na VPS |
| `Dockerfile` + `docker-compose.yml` | Deploy containerizado |
| `nomad_cli.py` | CLI para testes e administração |
| `test_suite.py` | Testes unitários e integração |
| `velocity.toml` | Configuração do proxy |

## 🔧 Configuração (Detalhe)

### API (nomad_api.py)

```bash
# Variáveis de ambiente
export NOMAD_API_KEY="sua-chave-super-secreta"
export NOMAD_STORAGE_BACKEND="local"  # ou "s3", "gdrive"
export NOMAD_STORAGE_PATH="/data/storage"

# Iniciar
python nomad_api.py
# ou com gunicorn (produção)
gunicorn -w 4 -b 0.0.0.0:5000 nomad_api:app
```

### World Manager (Persistência)

```python
from world_manager import WorldManager, StorageConfig

# S3
config = StorageConfig(
    backend="s3",
    api_url="http://seu-vps:5000",
    api_key="key",
    s3_bucket="seu-bucket",
    s3_region="us-east-1",
    s3_access_key="...",
    s3_secret_key="..."
)

# Google Drive
config = StorageConfig(
    backend="gdrive",
    api_url="http://seu-vps:5000",
    api_key="key",
    gdrive_folder_id="1ABC...",
    gdrive_service_account_json="/path/to/service-account.json"
)

# Local
config = StorageConfig(
    backend="local",
    api_url="http://seu-vps:5000",
    api_key="key",
    local_storage_path="/data/storage"
)

manager = WorldManager(config, world_dir="./world")

# Upload quando shutdown
result = manager.upload_world("world")
print(result["save_url"])  # URL para próximo host baixar
```

### Launcher (Tkinter UI)

Interface automática. Jogador:
1. Clica "Start Server"
2. Launcher verifica hardware
3. Baixa mundo (se necessário)
4. Inicia servidor Java
5. Abre túnel (ngrok/Cloudflare)
6. Notifica API
7. Heartbeat a cada 30s

Quando sair: salva mundo e faz upload.

### Plugin Velocity

```java
// Polling automático a cada 10s
// GET /api/state/active-host
// Atualiza backend server quando endpoint muda
```

## 🌐 Fluxo de Uso

### Cenário 1: Primeira vez, ninguém online

```
1. Player1 abre Launcher
2. Launcher pergunta à API: "Há host ativo?"
3. API responde: "Não"
4. Player1 clica "Start Server"
5. Launcher baixa mundo de /data/storage (ou seed vazio)
6. Launcher inicia Java com 2GB RAM
7. Launcher abre ngrok: endpoint=123.45.67.89:12345
8. Launcher POST /api/host/update-tunnel
   → Velocity atualiza backend para 123.45.67.89:12345
9. Todos os Minecraft clients conectam a 123.45.67.89:25565
   → Velocity roteia para 123.45.67.89:12345 (PC do Player1)
10. Player1 vê servidor rodando, joga com friends
```

### Cenário 2: Host sai, substituto assume

```
1. Player1 sai (mata Launcher)
2. Launcher faz shutdown gracefully:
   - Para servidor Java
   - Compacta /world em ZIP
   - Calcula SHA256
   - Faz upload para S3/GDrive
   - POST /api/host/shutdown (envia hash + URL)
3. API marca host como offline
4. Velocity perde backend
5. Player2 vê "No active host" no seu Launcher
6. Player2 clica "Start Server"
7. Launcher POST /api/state/world
   → Obtém URL do último save
8. Launcher baixa ZIP, extrai em ./world
9. Launcher inicia servidor (mesmo mundo!)
10. Nova túnel, novo IP dinâmico → Velocity atualiza
11. Jogo continua
```

### Cenário 3: Múltiplos hosts, qual usar?

API tem lógica de elegibilidade:
- **High tier** (16GB+ RAM, 8+ cores, 100GB+ disk) → preferência
- **Mid tier** (8GB RAM, 4+ cores, 50GB disk) → fallback
- **Low tier** (4GB RAM, 2+ cores, 20GB disk) → último recurso

Se Player1 (high) sai e Player2 (low) assume:
- Mundo roda mais lento, mas continua funcionando
- Quando Player1 volta (high), pode assumir de novo

## 🔐 Segurança

### Endpoints Públicos (sem autenticação)
- `GET /api/state/active-host` — qualquer um pode saber quem é o host
- `GET /api/state/world` — qualquer um pode ver estado do mundo
- `GET /api/health` — status da API
- `GET /api/whitelist/check/{uuid}` — verifica se jogador está whitelisted

### Endpoints Protegidos (requer API key)
- Todos em `POST` (register, update-tunnel, heartbeat, shutdown)
- Admin: `GET /api/state/all-hosts`, `/api/audit-log`
- Whitelist: `POST /api/whitelist/add`

**API Key** está em `$NOMAD_HOME/.env` — nunca commitar em git!

### SSL/TLS

```bash
# Configurar Let's Encrypt (nginx com certbot)
certbot --nginx -d seu-dominio.com

# Nginx vai redirecionar HTTP → HTTPS automaticamente
```

## 📊 Monitoramento

### Health Check
```bash
curl http://seu-vps:5000/api/health
# {"status": "ok", "timestamp": "2024-01-15T10:30:00"}
```

### CLI
```bash
python nomad_cli.py --api-key "sua-key" state active
python nomad_cli.py --api-key "sua-key" host list
python nomad_cli.py --api-key "sua-key" audit log --limit 100
```

### Logs
```bash
# API
tail -f /opt/nomad/logs/api.out.log

# Velocity
tail -f /opt/velocity/logs/velocity.log
```

## 🛠️ Troubleshooting

### "Launcher não conecta à API"
```bash
# Verificar firewall
sudo ufw status

# Testar conectividade
curl https://seu-vps.com/api/health

# Verificar API rodando
ps aux | grep gunicorn
```

### "Servidor não inicia"
```bash
# Verificar Java instalado
java -version

# Verificar server.jar existe
ls -la server.jar

# Testar offline-mode
echo "eula=true" > eula.txt
java -Xmx2G -jar server.jar nogui
```

### "Túnel não abre"
```bash
# ngrok
ngrok authtoken SUA_TOKEN
ngrok tcp localhost:25565

# Cloudflare
cloudflared login
cloudflared tunnel run nomad-server
```

### "Mundo não baixa"
```bash
# Verificar S3/GDrive credentials
# Verificar espaço em disco
df -h

# Testar upload manualmente
python -c "
from world_manager import WorldManager, StorageConfig
config = StorageConfig(backend='local', ...)
mgr = WorldManager(config)
mgr.upload_world('world')
"
```

## 📈 Scaling

### Múltiplos servidores backend
```toml
# velocity.toml
[servers]
server1 = "server1.exemplo.com:25565"
server2 = "server2.exemplo.com:25565"
server3 = "server3.exemplo.com:25565"

try = ["server1", "server2", "server3"]
```

### Load balancing (Velocity faz automático)
Velocity distribui jogadores entre backends disponíveis.

### Backup automático de worlds
```bash
# Cron job diário
0 3 * * * python -c "from world_manager import *; ..."
```

## 📝 Próximos Passos

1. **Deploy VPS**: `bash setup_vps.sh` ou `docker-compose up`
2. **Setup Velocity**: Copiar JAR e config, rodar
3. **Compilar Plugin**: Maven/Gradle, gerar JAR
4. **Distribuir Launcher**: Empacote como .exe (PyInstaller) ou .dmg
5. **Testar fluxo**: Player1 → Player2 substitui
6. **Monitorar**: Logs, alertas, backups

## 📚 Documentação Completa

- **Código-fonte**: Cada arquivo tem docstrings
- **Testes**: `test_suite.py` — exemplos de uso
- **CLI**: `nomad_cli.py --help`

## 🤝 Contribuindo

- Bug fixes: PR
- Novos backends: Estender `StorageBackend`
- Novos tunelamentos: Estender `TunnelManager`

---

**Made for Nomad Server — Dynamic Host Migration for Minecraft**
