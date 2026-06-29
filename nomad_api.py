"""
NOMAD SERVER - API DE ROTEAMENTO
Cloud/VPS: Flask + SQLite para gerenciar estado dinâmico do host
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import json
import os
import logging
import hashlib
import threading
from functools import wraps
from typing import Dict, Tuple, Optional

# ============================================================================
# SETUP
# ============================================================================

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "nomad_state.db"
API_KEY = os.getenv("NOMAD_API_KEY", "your-secret-key-here-change-in-production")
HOST_TIMEOUT_MINUTES = 5
WORLD_SAVE_TIMEOUT_MINUTES = 15

# ============================================================================
# DATABASE
# ============================================================================

def init_db():
    """Inicializa banco de dados com schema."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS hosts (
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS world_state (
        id INTEGER PRIMARY KEY,
        current_host_uuid TEXT,
        last_save_time TIMESTAMP,
        save_file_hash TEXT,
        save_file_url TEXT,
        total_players_online INTEGER,
        world_seed TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS player_whitelist (
        id INTEGER PRIMARY KEY,
        player_uuid TEXT UNIQUE,
        player_name TEXT,
        added_date TIMESTAMP,
        is_admin INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY,
        timestamp TIMESTAMP,
        action TEXT,
        player_uuid TEXT,
        details TEXT
    )''')
    
    conn.commit()
    conn.close()

def db_query(query: str, params: tuple = (), fetch_one: bool = False):
    """Helper seguro para queries."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(query, params)
        
        if "SELECT" in query.upper():
            result = c.fetchone() if fetch_one else c.fetchall()
            conn.close()
            return result
        else:
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None

# ============================================================================
# AUTENTICAÇÃO
# ============================================================================

def require_api_key(f):
    """Decorator para validar API key."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if not key or key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

def hash_uuid(uuid: str) -> str:
    """Hash seguro para UUIDs (evita logging de dados sensíveis)."""
    return hashlib.sha256(uuid.encode()).hexdigest()[:16]

# ============================================================================
# ENDPOINTS - HOST MANAGEMENT
# ============================================================================

@app.route("/api/host/register", methods=["POST"])
@require_api_key
def register_host():
    """
    Registra um novo host no cluster.
    Launcher envia: player_uuid, player_name, hardware_tier, version
    """
    try:
        data = request.get_json()
        player_uuid = data.get("player_uuid")
        player_name = data.get("player_name")
        hardware_tier = data.get("hardware_tier")  # "low", "mid", "high"
        version = data.get("version", "1.20.1")
        
        if not all([player_uuid, player_name, hardware_tier]):
            return jsonify({"error": "Missing fields"}), 400
        
        # Verifica se há host ativo
        active = db_query(
            "SELECT * FROM hosts WHERE status = 'active' AND last_heartbeat > datetime('now', '-5 minutes')",
            fetch_one=True
        )
        
        db_query(
            """INSERT OR REPLACE INTO hosts 
               (player_uuid, player_name, hardware_tier, status, version, last_heartbeat)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (player_uuid, player_name, hardware_tier, "pending", version)
        )
        
        db_query(
            "INSERT INTO audit_log (timestamp, action, player_uuid, details) VALUES (datetime('now'), ?, ?, ?)",
            ("REGISTER_HOST", player_uuid, f"tier={hardware_tier}")
        )
        
        logger.info(f"Host registered: {hash_uuid(player_uuid)} ({player_name})")
        
        return jsonify({
            "status": "registered",
            "active_host": {
                "uuid": active["player_uuid"] if active else None,
                "name": active["player_name"] if active else None,
            }
        }), 201
    
    except Exception as e:
        logger.error(f"Register host error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/host/update-tunnel", methods=["POST"])
@require_api_key
def update_tunnel():
    """
    Launcher envia IP + porta dinâmica do túnel (ngrok/Cloudflare).
    Velocity vai se reconectar a este endereço.
    """
    try:
        data = request.get_json()
        player_uuid = data.get("player_uuid")
        public_ip = data.get("public_ip")
        tunnel_port = data.get("tunnel_port", "25565")
        
        if not all([player_uuid, public_ip]):
            return jsonify({"error": "Missing fields"}), 400
        
        full_address = f"{public_ip}:{tunnel_port}"
        
        db_query(
            """UPDATE hosts SET 
               public_ip = ?, tunnel_port = ?, full_address = ?, 
               status = 'active', last_heartbeat = datetime('now')
               WHERE player_uuid = ?""",
            (public_ip, tunnel_port, full_address, player_uuid)
        )
        
        # Atualiza mundo_state
        db_query(
            "UPDATE world_state SET current_host_uuid = ?",
            (player_uuid,)
        )
        
        db_query(
            "INSERT INTO audit_log (timestamp, action, player_uuid, details) VALUES (datetime('now'), ?, ?, ?)",
            ("TUNNEL_UPDATE", player_uuid, f"endpoint={full_address}")
        )
        
        logger.info(f"Tunnel updated for {hash_uuid(player_uuid)}: {full_address}")
        
        return jsonify({
            "status": "updated",
            "server_endpoint": full_address,
            "velocity_will_reconnect_in_seconds": 10
        }), 200
    
    except Exception as e:
        logger.error(f"Update tunnel error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/host/heartbeat", methods=["POST"])
@require_api_key
def heartbeat():
    """
    Launcher envia heartbeat a cada 30 segundos para indicar que está vivo.
    """
    try:
        data = request.get_json()
        player_uuid = data.get("player_uuid")
        players_online = data.get("players_online", 0)
        tps = data.get("tps", 20)
        
        if not player_uuid:
            return jsonify({"error": "Missing player_uuid"}), 400
        
        db_query(
            """UPDATE hosts SET last_heartbeat = datetime('now')
               WHERE player_uuid = ?""",
            (player_uuid,)
        )
        
        db_query(
            "UPDATE world_state SET total_players_online = ?",
            (players_online,)
        )
        
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/host/shutdown", methods=["POST"])
@require_api_key
def shutdown_host():
    """
    Host vai desligar: envia Save do mundo antes.
    """
    try:
        data = request.get_json()
        player_uuid = data.get("player_uuid")
        save_file_hash = data.get("save_file_hash")
        save_file_url = data.get("save_file_url")
        
        if not player_uuid:
            return jsonify({"error": "Missing player_uuid"}), 400
        
        db_query(
            """UPDATE hosts SET status = 'offline', last_heartbeat = datetime('now')
               WHERE player_uuid = ?""",
            (player_uuid,)
        )
        
        db_query(
            """UPDATE world_state SET 
               last_save_time = datetime('now'), 
               save_file_hash = ?,
               save_file_url = ?""",
            (save_file_hash, save_file_url)
        )
        
        db_query(
            "INSERT INTO audit_log (timestamp, action, player_uuid, details) VALUES (datetime('now'), ?, ?, ?)",
            ("HOST_SHUTDOWN", player_uuid, f"hash={save_file_hash}")
        )
        
        logger.info(f"Host shutdown: {hash_uuid(player_uuid)}")
        
        return jsonify({"status": "shutdown_confirmed"}), 200
    
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# ENDPOINTS - STATE & QUERIES
# ============================================================================

@app.route("/api/state/active-host", methods=["GET"])
def get_active_host():
    """
    Clients query: Qual é o host ativo agora?
    Responde com endpoint do Velocity (que redireciona).
    """
    try:
        host = db_query(
            """SELECT * FROM hosts WHERE status = 'active' 
               AND last_heartbeat > datetime('now', '-5 minutes')
               ORDER BY last_heartbeat DESC LIMIT 1""",
            fetch_one=True
        )
        
        if not host:
            return jsonify({
                "active": False,
                "message": "No active host. Starting a new one..."
            }), 200
        
        return jsonify({
            "active": True,
            "host": {
                "name": host["player_name"],
                "endpoint": host["full_address"],
                "tier": host["hardware_tier"],
                "uptime_minutes": (
                    (datetime.now() - datetime.fromisoformat(host["last_heartbeat"])).total_seconds() / 60
                )
            }
        }), 200
    
    except Exception as e:
        logger.error(f"Get active host error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/state/world", methods=["GET"])
def get_world_state():
    """
    Retorna estado do mundo: last save, hash, players online.
    """
    try:
        world = db_query(
            "SELECT * FROM world_state LIMIT 1",
            fetch_one=True
        )
        
        if not world:
            return jsonify({
                "exists": False,
                "message": "World not initialized"
            }), 200
        
        return jsonify({
            "exists": True,
            "current_host": world["current_host_uuid"],
            "last_save": world["last_save_time"],
            "save_hash": world["save_file_hash"],
            "save_url": world["save_file_url"],
            "players_online": world["total_players_online"]
        }), 200
    
    except Exception as e:
        logger.error(f"Get world state error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/state/all-hosts", methods=["GET"])
@require_api_key
def get_all_hosts():
    """
    Admin only: Lista todos os hosts registrados.
    """
    try:
        hosts = db_query(
            """SELECT player_uuid, player_name, status, hardware_tier, 
                      full_address, last_heartbeat FROM hosts ORDER BY last_heartbeat DESC"""
        )
        
        return jsonify({
            "total": len(hosts) if hosts else 0,
            "hosts": [dict(h) for h in (hosts or [])]
        }), 200
    
    except Exception as e:
        logger.error(f"Get all hosts error: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# ENDPOINTS - WHITELIST
# ============================================================================

@app.route("/api/whitelist/add", methods=["POST"])
@require_api_key
def add_whitelist():
    """
    Admin adds player ao whitelist.
    """
    try:
        data = request.get_json()
        player_uuid = data.get("player_uuid")
        player_name = data.get("player_name")
        
        if not all([player_uuid, player_name]):
            return jsonify({"error": "Missing fields"}), 400
        
        db_query(
            """INSERT OR REPLACE INTO player_whitelist 
               (player_uuid, player_name, added_date)
               VALUES (?, ?, datetime('now'))""",
            (player_uuid, player_name)
        )
        
        return jsonify({"status": "added"}), 201
    
    except Exception as e:
        logger.error(f"Add whitelist error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/whitelist/check/<player_uuid>", methods=["GET"])
def check_whitelist(player_uuid):
    """
    Launcher/Server verifica se player está whitelisted.
    """
    try:
        player = db_query(
            "SELECT * FROM player_whitelist WHERE player_uuid = ?",
            (player_uuid,),
            fetch_one=True
        )
        
        return jsonify({
            "whitelisted": player is not None,
            "player_name": player["player_name"] if player else None
        }), 200
    
    except Exception as e:
        logger.error(f"Check whitelist error: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH & MONITORING
# ============================================================================

@app.route("/api/health", methods=["GET"])
def health_check():
    """
    Health check para load balancer/monitoring.
    """
    try:
        # Testa conexão DB
        db_query("SELECT 1")
        
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/audit-log", methods=["GET"])
@require_api_key
def get_audit_log():
    """
    Retorna últimas 100 ações registradas.
    """
    try:
        logs = db_query(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 100"
        )
        
        return jsonify({
            "logs": [dict(log) for log in (logs or [])]
        }), 200
    
    except Exception as e:
        logger.error(f"Get audit log error: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# BACKGROUND TASKS
# ============================================================================

def cleanup_inactive_hosts():
    """
    A cada 1 minuto, marca hosts sem heartbeat como offline.
    """
    while True:
        try:
            db_query(
                """UPDATE hosts SET status = 'offline' 
                   WHERE last_heartbeat < datetime('now', '-5 minutes') 
                   AND status = 'active'"""
            )
            threading.Event().wait(60)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    init_db()
    
    # Inicia thread de limpeza
    cleanup_thread = threading.Thread(target=cleanup_inactive_hosts, daemon=True)
    cleanup_thread.start()
    
    # Em produção: usar gunicorn ou waitress
    app.run(host="0.0.0.0", port=5000, debug=False)
