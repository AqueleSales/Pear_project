"""
NOMAD SERVER - API DE ROTEAMENTO (REFACTOR: FASTAPI)
Alta performance, Assíncrona e com concorrência SQLite otimizada.
"""

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from datetime import datetime
import aiosqlite
import hashlib
import os
import asyncio
import logging
from typing import Optional, List

# ============================================================================
# SETUP & CONFIG
# ============================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Nomad Server API", version="2.0.0")

DB_PATH = "nomad_state.db"
API_KEY = os.getenv("NOMAD_API_KEY", "your-secret-key-here-change-in-production")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# ============================================================================
# MODELS (PYDANTIC VALIDAÇÃO STRICT)
# ============================================================================

class HostRegisterReq(BaseModel):
    player_uuid: str
    player_name: str
    hardware_tier: str
    version: str = "1.20.1"

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

class WhitelistReq(BaseModel):
    player_uuid: str
    player_name: str

# ============================================================================
# DATABASE ASYNC CORE
# ============================================================================

async def get_db():
    """Gerencia a conexão assíncrona com o banco."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    """Inicializa as tabelas e otimiza o SQLite para concorrência (WAL)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Ativa Write-Ahead Logging para concorrência e remove delay de disco
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")

        await db.execute('''CREATE TABLE IF NOT EXISTS hosts (
            id INTEGER PRIMARY KEY,
            player_uuid TEXT UNIQUE,
            player_name TEXT,
            public_ip TEXT,
            tunnel_port TEXT,
            full_address TEXT,
            hardware_tier TEXT,
            last_heartbeat TIMESTAMP,
            status TEXT,
            version TEXT
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS world_state (
            id INTEGER PRIMARY KEY,
            current_host_uuid TEXT,
            last_save_time TIMESTAMP,
            save_file_hash TEXT,
            save_file_url TEXT,
            total_players_online INTEGER,
            world_seed TEXT
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP,
            action TEXT,
            player_uuid TEXT,
            details TEXT
        )''')

        # Garante que o world_state tenha sempre 1 linha
        async with db.execute("SELECT COUNT(*) FROM world_state") as cursor:
            count = await cursor.fetchone()
            if count[0] == 0:
                await db.execute("INSERT INTO world_state (total_players_online) VALUES (0)")

        await db.commit()

# ============================================================================
# UTILS & AUTH
# ============================================================================

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

def hash_uuid(uuid: str) -> str:
    return hashlib.sha256(uuid.encode()).hexdigest()[:16]

async def log_audit(db: aiosqlite.Connection, action: str, player_uuid: str, details: str):
    await db.execute(
        "INSERT INTO audit_log (timestamp, action, player_uuid, details) VALUES (datetime('now'), ?, ?, ?)",
        (action, player_uuid, details)
    )

# ============================================================================
# ENDPOINTS - HOST MANAGEMENT (PROTECTED)
# ============================================================================

@app.post("/api/host/register", status_code=201)
async def register_host(req: HostRegisterReq, db: aiosqlite.Connection = Depends(get_db), _: str = Depends(verify_api_key)):
    try:
        # Verifica se já existe um host ativo
        async with db.execute(
            "SELECT player_uuid, player_name FROM hosts WHERE status = 'active' AND last_heartbeat > datetime('now', '-5 minutes')"
        ) as cursor:
            active = await cursor.fetchone()

        await db.execute(
            """INSERT OR REPLACE INTO hosts 
               (player_uuid, player_name, hardware_tier, status, version, last_heartbeat)
               VALUES (?, ?, ?, 'pending', ?, datetime('now'))""",
            (req.player_uuid, req.player_name, req.hardware_tier, req.version)
        )
        await log_audit(db, "REGISTER_HOST", req.player_uuid, f"tier={req.hardware_tier}")
        await db.commit()

        logger.info(f"Host registered: {hash_uuid(req.player_uuid)} ({req.player_name})")

        return {
            "status": "registered",
            "active_host": {"uuid": active["player_uuid"], "name": active["player_name"]} if active else None
        }
    except Exception as e:
        logger.error(f"Error registering host: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/api/host/update-tunnel")
async def update_tunnel(req: TunnelUpdateReq, db: aiosqlite.Connection = Depends(get_db), _: str = Depends(verify_api_key)):
    full_address = f"{req.public_ip}:{req.tunnel_port}"
    try:
        await db.execute(
            """UPDATE hosts SET 
               public_ip = ?, tunnel_port = ?, full_address = ?, 
               status = 'active', last_heartbeat = datetime('now')
               WHERE player_uuid = ?""",
            (req.public_ip, req.tunnel_port, full_address, req.player_uuid)
        )
        await db.execute("UPDATE world_state SET current_host_uuid = ?", (req.player_uuid,))
        await log_audit(db, "TUNNEL_UPDATE", req.player_uuid, f"endpoint={full_address}")
        await db.commit()

        logger.info(f"Tunnel updated for {hash_uuid(req.player_uuid)}: {full_address}")
        return {"status": "updated", "server_endpoint": full_address}
    except Exception as e:
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
    await db.execute(
        """UPDATE world_state SET last_save_time = datetime('now'), save_file_hash = ?, save_file_url = ?""",
        (req.save_file_hash, req.save_file_url)
    )
    await log_audit(db, "HOST_SHUTDOWN", req.player_uuid, f"hash={req.save_file_hash}")
    await db.commit()
    return {"status": "shutdown_confirmed"}

# ============================================================================
# ENDPOINTS - PUBLIC STATE (USADO PELO LAUNCHER E VELOCITY)
# ============================================================================

@app.get("/api/state/active-host")
async def get_active_host(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        """SELECT player_name, full_address, hardware_tier, last_heartbeat 
           FROM hosts WHERE status = 'active' AND last_heartbeat > datetime('now', '-5 minutes')
           ORDER BY last_heartbeat DESC LIMIT 1"""
    ) as cursor:
        host = await cursor.fetchone()

    if not host:
        return {"active": False, "message": "No active host."}

    uptime_minutes = (datetime.now() - datetime.fromisoformat(host["last_heartbeat"])).total_seconds() / 60
    return {
        "active": True,
        "host": {
            "name": host["player_name"],
            "endpoint": host["full_address"],
            "tier": host["hardware_tier"],
            "uptime_minutes": round(uptime_minutes, 1)
        }
    }

@app.get("/api/state/world")
async def get_world_state(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM world_state LIMIT 1") as cursor:
        world = await cursor.fetchone()

    if not world or not world["save_file_url"]:
        return {"exists": False, "message": "World not initialized or no backups yet."}

    return {
        "exists": True,
        "current_host": world["current_host_uuid"],
        "last_save": world["last_save_time"],
        "save_hash": world["save_file_hash"],
        "save_url": world["save_file_url"],
        "players_online": world["total_players_online"]
    }

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# ============================================================================
# BACKGROUND TASKS (CLEANUP)
# ============================================================================

async def cleanup_inactive_hosts():
    """Roda infinitamente em background, limpando hosts mortos."""
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """UPDATE hosts SET status = 'offline' 
                       WHERE last_heartbeat < datetime('now', '-5 minutes') 
                       AND status = 'active'"""
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    await init_db()
    asyncio.create_task(cleanup_inactive_hosts())

# Executar localmente para testes:
# uvicorn nomad_api:app --reload --host 0.0.0.0 --port 5000