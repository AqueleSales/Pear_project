"""
NOMAD SERVER - API DE ROTEAMENTO V0.2
Integração automática de rede com Oracle Cloud via SSH.
Centralizada: Evita Race Conditions no Velocity
"""

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime
import aiosqlite
import hashlib
import os
import asyncio
import logging
import subprocess
from pathlib import Path

# ============================================================================
# SETUP & CONFIG
# ============================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Nomad Server API", version="2.0.0")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "nomad_state.db")
API_KEY = os.getenv("NOMAD_API_KEY", "minecraftpear2026")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# Configurações da Nuvem Oracle
ORACLE_IP = "163.176.54.0"
SSH_KEY_PATH = "ssh-key-2026-07-02.key"

# ============================================================================
# MODELS
# ============================================================================

class HostRegisterReq(BaseModel):
    player_uuid: str
    player_name: str
    hardware_tier: str
    version: str = "1.21.1"

class TunnelUpdateReq(BaseModel):
    player_uuid: str
    public_ip: str
    tunnel_port: str = "25565"

class HeartbeatReq(BaseModel):
    player_uuid: str
    players_online: int = 0
    tps: float = 20.0

class ShutdownReq(BaseModel):
    player_uuid: str
    save_file_hash: str
    save_file_url: str

# ============================================================================
# DATABASE ASYNC CORE
# ============================================================================

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")

        await db.execute('''CREATE TABLE IF NOT EXISTS hosts (
            id INTEGER PRIMARY KEY, player_uuid TEXT UNIQUE, player_name TEXT,
            public_ip TEXT, tunnel_port TEXT, full_address TEXT, hardware_tier TEXT,
            last_heartbeat TIMESTAMP, status TEXT, version TEXT
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS world_state (
            id INTEGER PRIMARY KEY, current_host_uuid TEXT, last_save_time TIMESTAMP,
            save_file_hash TEXT, save_file_url TEXT, total_players_online INTEGER, world_seed TEXT
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY, timestamp TIMESTAMP, action TEXT, player_uuid TEXT, details TEXT
        )''')

        async with db.execute("SELECT COUNT(*) FROM world_state") as cursor:
            if (await cursor.fetchone())[0] == 0:
                await db.execute("INSERT INTO world_state (total_players_online) VALUES (0)")
        await db.commit()

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

def hash_uuid(uuid: str) -> str:
    return hashlib.sha256(uuid.encode()).hexdigest()[:16]

async def log_audit(db: aiosqlite.Connection, action: str, player_uuid: str, details: str):
    await db.execute("INSERT INTO audit_log (timestamp, action, player_uuid, details) VALUES (datetime('now'), ?, ?, ?)", (action, player_uuid, details))

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.post("/api/host/register", status_code=201)
async def register_host(req: HostRegisterReq, db: aiosqlite.Connection = Depends(get_db), _: str = Depends(verify_api_key)):
    await db.execute("""INSERT OR REPLACE INTO hosts (player_uuid, player_name, hardware_tier, status, version, last_heartbeat)
                        VALUES (?, ?, ?, 'pending', ?, datetime('now'))""",
                     (req.player_uuid, req.player_name, req.hardware_tier, req.version))
    await log_audit(db, "REGISTER_HOST", req.player_uuid, f"tier={req.hardware_tier}")
    await db.commit()
    logger.info(f"Host registrado: {req.player_name}")
    return {"status": "registered"}

@app.post("/api/host/update-tunnel")
async def update_tunnel(req: TunnelUpdateReq, db: aiosqlite.Connection = Depends(get_db), _: str = Depends(verify_api_key)):
    full_address = f"{req.public_ip}:{req.tunnel_port}"
    try:
        # 1. Recupera o nome do jogador para o current_host.txt (Compatibilidade com Launcher)
        player_name = req.player_uuid # Fallback
        async with db.execute("SELECT player_name FROM hosts WHERE player_uuid = ?", (req.player_uuid,)) as cursor:
            row = await cursor.fetchone()
            if row:
                player_name = row[0]

        # 2. Atualiza Banco Local
        await db.execute("""UPDATE hosts SET public_ip = ?, tunnel_port = ?, full_address = ?, status = 'active', last_heartbeat = datetime('now') WHERE player_uuid = ?""",
                         (req.public_ip, req.tunnel_port, full_address, req.player_uuid))
        await db.execute("UPDATE world_state SET current_host_uuid = ?", (req.player_uuid,))
        await log_audit(db, "TUNNEL_UPDATE", req.player_uuid, f"endpoint={full_address}")
        await db.commit()

        # 3. Automação SSH Robusta para Oracle (O pulo do gato - Correção Race Condition)
        logger.info(f"Sincronizando configurações na Oracle para: {full_address}")

        # Utilizando SED para edição segura de texto via bash remoto
        remote_command = f"""
        cd ~/velocity
        
        # Injeta IP e configurações vitais no TOML
        sed -i -E 's/^(nomad-backend\\s*=\\s*).*$/\\1"{full_address}"/' velocity.toml
        sed -i -E 's/^(online-mode\\s*=\\s*).*$/\\1false/' velocity.toml
        sed -i -E 's/^(force-key-authentication\\s*=\\s*).*$/\\1false/' velocity.toml
        sed -i -E 's/^(player-info-forwarding-mode\\s*=\\s*).*$/\\1"modern"/' velocity.toml
        
        # Atualiza quem é o Host atual para o painel
        echo "{player_name}|{full_address}" > current_host.txt
        
        # Reinicia o Velocity de forma limpa (desconectando dos processos filhos)
        pkill -9 -f velocity.jar || true
        rm -f velocity.log
        sleep 1
        nohup java -jar velocity.jar > velocity.log 2>&1 </dev/null &
        """

        # Executa sincronamente aguardando conclusão/erro (timeout de 15s)
        try:
            subprocess.run([
                "ssh", "-i", SSH_KEY_PATH,
                "-o", "StrictHostKeyChecking=no",
                f"ubuntu@{ORACLE_IP}", remote_command
            ], check=True, timeout=15, capture_output=True)

            logger.info("Sincronização com Oracle concluída e Proxy reiniciado.")
            return {"status": "updated", "server_endpoint": full_address, "cloud_sync": True}

        except subprocess.CalledProcessError as ssh_err:
            logger.error(f"Falha na comunicação SSH com a Nuvem: {ssh_err.stderr.decode('utf-8')}")
            raise Exception("Falha de comunicação SSH com a Oracle.")

    except Exception as e:
        logger.error(f"Erro no túnel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/host/heartbeat")
async def heartbeat(req: HeartbeatReq, db: aiosqlite.Connection = Depends(get_db), _: str = Depends(verify_api_key)):
    await db.execute("UPDATE hosts SET last_heartbeat = datetime('now') WHERE player_uuid = ?", (req.player_uuid,))
    await db.execute("UPDATE world_state SET total_players_online = ?", (req.players_online,))
    await db.commit()
    return {"status": "ok"}

@app.post("/api/host/shutdown")
async def shutdown_host(req: ShutdownReq, db: aiosqlite.Connection = Depends(get_db), _: str = Depends(verify_api_key)):
    await db.execute("UPDATE hosts SET status = 'offline', last_heartbeat = datetime('now') WHERE player_uuid = ?", (req.player_uuid,))
    await db.execute("UPDATE world_state SET last_save_time = datetime('now'), save_file_hash = ?, save_file_url = ?", (req.save_file_hash, req.save_file_url))
    await log_audit(db, "HOST_SHUTDOWN", req.player_uuid, f"hash={req.save_file_hash}")
    await db.commit()
    return {"status": "shutdown_confirmed"}

@app.on_event("startup")
async def startup_event():
    await init_db()