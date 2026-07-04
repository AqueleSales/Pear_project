"""
NOMAD SERVER - API DE ROTEAMENTO V0.2
Integração automática de rede com Oracle Cloud via SSH.
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
        # 1. Atualiza Banco Local
        await db.execute("""UPDATE hosts SET public_ip = ?, tunnel_port = ?, full_address = ?, status = 'active', last_heartbeat = datetime('now') WHERE player_uuid = ?""",
                         (req.public_ip, req.tunnel_port, full_address, req.player_uuid))
        await db.execute("UPDATE world_state SET current_host_uuid = ?", (req.player_uuid,))
        await log_audit(db, "TUNNEL_UPDATE", req.player_uuid, f"endpoint={full_address}")
        await db.commit()

        # 2. Automação SSH para Oracle (O pulo do gato)
        logger.info(f"Sincronizando novo IP ({full_address}) com a Nuvem Oracle...")

        remote_command = f"""
        sed -i 's/^nomad-backend = .*/nomad-backend = "{full_address}"/' ~/velocity/velocity.toml
        pkill -f velocity.jar
        cd ~/velocity && nohup java -jar velocity.jar > velocity.log 2>&1 &
        """

        subprocess.Popen([
            "ssh", "-i", SSH_KEY_PATH,
            "-o", "StrictHostKeyChecking=no",
            f"ubuntu@{ORACLE_IP}", remote_command
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logger.info("Sincronização com Oracle disparada com sucesso!")
        return {"status": "updated", "server_endpoint": full_address, "cloud_sync": True}
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