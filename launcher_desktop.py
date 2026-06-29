"""
NOMAD SERVER - LAUNCHER DESKTOP
Tkinter UI + lógica: hardware check, download, server start, tunneling, heartbeat
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import subprocess
import psutil
import requests
import json
import os
import time
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass
import platform

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG
# ============================================================================

@dataclass
class LauncherConfig:
    api_url: str = "http://your-vps.com:5000"
    api_key: str = "your-api-key"
    player_name: str = ""
    player_uuid: str = ""
    minecraft_server_jar: str = "./server.jar"
    world_dir: str = "./world"
    java_path: str = "java"
    tunnel_service: str = "ngrok"  # ou "cloudflare", "playit"
    tunnel_token: str = ""
    server_port: int = 25565
    server_memory_mb: int = 2048
    server_eula: bool = True

class ConfigManager:
    """Gerencia config do Launcher."""
    
    CONFIG_PATH = Path.home() / ".nomad" / "launcher_config.json"
    
    @classmethod
    def load(cls) -> LauncherConfig:
        if cls.CONFIG_PATH.exists():
            with open(cls.CONFIG_PATH, "r") as f:
                data = json.load(f)
                return LauncherConfig(**data)
        return LauncherConfig()
    
    @classmethod
    def save(cls, config: LauncherConfig):
        cls.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(cls.CONFIG_PATH, "w") as f:
            json.dump(vars(config), f, indent=2)

# ============================================================================
# HARDWARE DETECTION
# ============================================================================

class HardwareAnalyzer:
    """Analisa hardware local."""
    
    @staticmethod
    def get_system_info() -> Dict:
        """Retorna info de hardware."""
        return {
            "cpu_cores": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_total_gb": psutil.virtual_memory().total / 1024 / 1024 / 1024,
            "ram_available_gb": psutil.virtual_memory().available / 1024 / 1024 / 1024,
            "disk_total_gb": psutil.disk_usage("/").total / 1024 / 1024 / 1024,
            "disk_free_gb": psutil.disk_usage("/").free / 1024 / 1024 / 1024,
            "os": platform.system(),
        }
    
    @staticmethod
    def get_tier(info: Dict) -> str:
        """Classifica hardware em tier."""
        ram_gb = info["ram_total_gb"]
        cores = info["cpu_cores"]
        disk_gb = info["disk_total_gb"]
        
        if ram_gb >= 16 and cores >= 8 and disk_gb >= 100:
            return "high"
        elif ram_gb >= 8 and cores >= 4 and disk_gb >= 50:
            return "mid"
        else:
            return "low"
    
    @staticmethod
    def is_eligible(info: Dict) -> bool:
        """Verifica se hardware é elegível para host."""
        return (
            info["ram_available_gb"] >= 4 and
            info["disk_free_gb"] >= 20 and
            info["cpu_cores"] >= 2
        )

# ============================================================================
# NOMAD API CLIENT
# ============================================================================

class NomadAPIClient:
    """Cliente para API do Nomad."""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})
    
    def register_host(self, player_uuid: str, player_name: str, tier: str, version: str) -> Dict:
        """Registra como novo host."""
        try:
            resp = self.session.post(
                f"{self.api_url}/api/host/register",
                json={
                    "player_uuid": player_uuid,
                    "player_name": player_name,
                    "hardware_tier": tier,
                    "version": version
                },
                timeout=5
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Register host error: {e}")
            return {"error": str(e)}
    
    def update_tunnel(self, player_uuid: str, public_ip: str, tunnel_port: str) -> Dict:
        """Notifica API sobre IP dinâmico do túnel."""
        try:
            resp = self.session.post(
                f"{self.api_url}/api/host/update-tunnel",
                json={
                    "player_uuid": player_uuid,
                    "public_ip": public_ip,
                    "tunnel_port": tunnel_port
                },
                timeout=5
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Update tunnel error: {e}")
            return {"error": str(e)}
    
    def send_heartbeat(self, player_uuid: str, players_online: int = 0, tps: float = 20) -> Dict:
        """Envia heartbeat a cada 30s."""
        try:
            resp = self.session.post(
                f"{self.api_url}/api/host/heartbeat",
                json={
                    "player_uuid": player_uuid,
                    "players_online": players_online,
                    "tps": tps
                },
                timeout=5
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            return {"error": str(e)}
    
    def get_active_host(self) -> Dict:
        """Obtém host ativo."""
        try:
            resp = self.session.get(
                f"{self.api_url}/api/state/active-host",
                timeout=5
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Get active host error: {e}")
            return {"error": str(e)}
    
    def get_world_state(self) -> Dict:
        """Obtém estado do mundo."""
        try:
            resp = self.session.get(
                f"{self.api_url}/api/state/world",
                timeout=5
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Get world state error: {e}")
            return {"error": str(e)}
    
    def shutdown_host(self, player_uuid: str, save_hash: str, save_url: str) -> Dict:
        """Notifica API que vai desligar."""
        try:
            resp = self.session.post(
                f"{self.api_url}/api/host/shutdown",
                json={
                    "player_uuid": player_uuid,
                    "save_file_hash": save_hash,
                    "save_file_url": save_url
                },
                timeout=5
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
            return {"error": str(e)}

# ============================================================================
# TUNNELING MANAGERS
# ============================================================================

class TunnelManager:
    """Base class para gerenciar túneis."""
    
    def __init__(self, server_port: int = 25565):
        self.server_port = server_port
        self.process = None
        self.public_ip = None
        self.tunnel_port = None
    
    def start(self) -> bool:
        """Inicia túnel."""
        raise NotImplementedError
    
    def stop(self) -> bool:
        """Para túnel."""
        if self.process:
            self.process.terminate()
            return True
        return False
    
    def get_endpoint(self) -> Optional[str]:
        """Retorna endpoint público."""
        raise NotImplementedError

class NgrokTunnel(TunnelManager):
    """Gerencia ngrok."""
    
    def __init__(self, server_port: int, token: str):
        super().__init__(server_port)
        self.token = token
    
    def start(self) -> bool:
        try:
            # Autentica com ngrok
            os.system(f"ngrok authtoken {self.token}")
            
            # Inicia túnel
            self.process = subprocess.Popen(
                ["ngrok", "tcp", f"localhost:{self.server_port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            time.sleep(2)
            
            # Obtém endpoint via API do ngrok
            try:
                resp = requests.get("http://localhost:4040/api/tunnels")
                tunnels = resp.json().get("tunnels", [])
                if tunnels:
                    # ngrok retorna algo como "tcp://0.tcp.ngrok.io:12345"
                    public_url = tunnels[0]["public_url"]
                    parts = public_url.split("://")[1].split(":")
                    self.public_ip = parts[0]
                    self.tunnel_port = parts[1] if len(parts) > 1 else "25565"
                    logger.info(f"Ngrok tunnel: {self.public_ip}:{self.tunnel_port}")
                    return True
            except Exception as e:
                logger.error(f"Ngrok API error: {e}")
                return False
        
        except Exception as e:
            logger.error(f"Ngrok start error: {e}")
            return False
    
    def get_endpoint(self) -> Optional[str]:
        if self.public_ip and self.tunnel_port:
            return f"{self.public_ip}:{self.tunnel_port}"
        return None

class CloudflareTunnel(TunnelManager):
    """Gerencia Cloudflare Tunnels."""
    
    def __init__(self, server_port: int, tunnel_token: str):
        super().__init__(server_port)
        self.tunnel_token = tunnel_token
    
    def start(self) -> bool:
        try:
            # cloudflared cria túnel via config file
            config_content = f"""tunnel: nomad-server
credentials-file: ~/.cloudflare/nomad-server.json

ingress:
  - service: tcp://localhost:{self.server_port}
"""
            config_path = Path.home() / ".cloudflare" / "nomad-tunnel.yml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(config_content)
            
            # Inicia cloudflared
            self.process = subprocess.Popen(
                ["cloudflared", "tunnel", "run", "nomad-server", "-f", str(config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            time.sleep(3)
            logger.info("Cloudflare tunnel started")
            return True
        
        except Exception as e:
            logger.error(f"Cloudflare tunnel error: {e}")
            return False
    
    def get_endpoint(self) -> Optional[str]:
        # Cloudflare usa domínio customizado (trouted.dev, cloudflare)
        # Necessário consultar dashboard ou usar API
        return "your-tunnel.trycloudflare.com"

# ============================================================================
# SERVER MANAGER
# ============================================================================

class ServerManager:
    """Gerencia inicialização/parada do servidor Minecraft."""
    
    def __init__(self, config: LauncherConfig):
        self.config = config
        self.process = None
        self.world_manager = None
    
    def start_server(self) -> bool:
        """Inicia servidor Java."""
        try:
            # Verifica se jar existe
            if not Path(self.config.minecraft_server_jar).exists():
                logger.error(f"Server JAR not found: {self.config.minecraft_server_jar}")
                return False
            
            # Cria diretório world se não existir
            Path(self.config.world_dir).mkdir(parents=True, exist_ok=True)
            
            # Aceita EULA
            eula_path = Path(self.config.world_dir) / ".." / "eula.txt"
            if not eula_path.exists():
                eula_path.parent.mkdir(parents=True, exist_ok=True)
                eula_path.write_text("eula=true\n")
            
            # Construi comando
            jvm_args = [
                self.config.java_path,
                f"-Xmx{self.config.server_memory_mb}M",
                f"-Xms{self.config.server_memory_mb // 2}M",
                "-jar",
                self.config.minecraft_server_jar,
                "nogui"
            ]
            
            logger.info(f"Starting server: {' '.join(jvm_args)}")
            
            self.process = subprocess.Popen(
                jvm_args,
                cwd=str(Path(self.config.world_dir).parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            logger.info("Server started")
            return True
        
        except Exception as e:
            logger.error(f"Server start error: {e}")
            return False
    
    def stop_server(self) -> bool:
        """Para servidor gracefully."""
        if not self.process:
            return False
        
        try:
            # Envia /stop command via stdin
            self.process.stdin.write("stop\n")
            self.process.stdin.flush()
            
            # Aguarda 10s para shutdown
            self.process.wait(timeout=10)
            logger.info("Server stopped")
            return True
        
        except subprocess.TimeoutExpired:
            # Kill se não parou
            self.process.kill()
            logger.warning("Server force killed")
            return True
        
        except Exception as e:
            logger.error(f"Server stop error: {e}")
            return False
    
    def is_running(self) -> bool:
        return self.process and self.process.poll() is None

# ============================================================================
# MAIN LAUNCHER UI
# ============================================================================

class NomadLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Nomad Server Launcher")
        self.geometry("900x700")
        self.resizable(False, False)
        
        self.config = ConfigManager.load()
        self.api_client = NomadAPIClient(self.config.api_url, self.config.api_key)
        self.server_manager = ServerManager(self.config)
        self.tunnel_manager = None
        self.heartbeat_thread = None
        self.running = False
        
        # Gera UUID se não existe
        if not self.config.player_uuid:
            self.config.player_uuid = str(uuid.uuid4())
            ConfigManager.save(self.config)
        
        self._build_ui()
        self._refresh_status()
    
    def _build_ui(self):
        """Constrói interface."""
        
        # === HEADER ===
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(header, text="NOMAD SERVER LAUNCHER", font=("Arial", 14, "bold")).pack(side="left")
        ttk.Label(header, text=f"UUID: {self.config.player_uuid[:8]}...", font=("Arial", 8)).pack(side="right", padx=5)
        
        # === SECTION: HARDWARE ===
        hw_frame = ttk.LabelFrame(self, text="Hardware Analysis", padding=10)
        hw_frame.pack(fill="x", padx=10, pady=5)
        
        self.hw_text = tk.Text(hw_frame, height=6, width=80, state="disabled")
        self.hw_text.pack(fill="both")
        
        ttk.Button(hw_frame, text="Refresh Hardware", command=self._refresh_hardware).pack(pady=5)
        
        # === SECTION: SETTINGS ===
        settings_frame = ttk.LabelFrame(self, text="Settings", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(settings_frame, text="Player Name:").grid(row=0, column=0, sticky="w")
        self.player_name_var = tk.StringVar(value=self.config.player_name)
        ttk.Entry(settings_frame, textvariable=self.player_name_var, width=30).grid(row=0, column=1, sticky="ew")
        
        ttk.Label(settings_frame, text="API URL:").grid(row=1, column=0, sticky="w")
        self.api_url_var = tk.StringVar(value=self.config.api_url)
        ttk.Entry(settings_frame, textvariable=self.api_url_var, width=30).grid(row=1, column=1, sticky="ew")
        
        ttk.Label(settings_frame, text="Server Memory (MB):").grid(row=2, column=0, sticky="w")
        self.memory_var = tk.StringVar(value=str(self.config.server_memory_mb))
        ttk.Spinbox(settings_frame, from_=512, to=16000, textvariable=self.memory_var, width=10).grid(row=2, column=1, sticky="w")
        
        ttk.Button(settings_frame, text="Save Settings", command=self._save_settings).grid(row=3, column=1, sticky="ew", pady=5)
        
        # === SECTION: STATUS ===
        status_frame = ttk.LabelFrame(self, text="Status", padding=10)
        status_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.status_text = scrolledtext.ScrolledText(status_frame, height=10, width=80, state="disabled")
        self.status_text.pack(fill="both", expand=True)
        
        # === SECTION: CONTROLS ===
        controls_frame = ttk.Frame(self, padding=10)
        controls_frame.pack(fill="x")
        
        self.start_btn = ttk.Button(controls_frame, text="Start Server", command=self._start_server)
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(controls_frame, text="Stop Server", command=self._stop_server, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        
        ttk.Button(controls_frame, text="Download World", command=self._download_world).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Exit", command=self._on_closing).pack(side="right", padx=5)
    
    def _log(self, message: str, level: str = "INFO"):
        """Adiciona mensagem ao status text."""
        self.status_text.config(state="normal")
        self.status_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {level}: {message}\n")
        self.status_text.see("end")
        self.status_text.config(state="disabled")
    
    def _refresh_hardware(self):
        """Atualiza info de hardware."""
        info = HardwareAnalyzer.get_system_info()
        tier = HardwareAnalyzer.get_tier(info)
        eligible = HardwareAnalyzer.is_eligible(info)
        
        hw_info = f"""CPU: {info['cpu_cores']} cores @ {info['cpu_percent']:.1f}%
RAM: {info['ram_total_gb']:.1f} GB total ({info['ram_available_gb']:.1f} GB available)
DISK: {info['disk_total_gb']:.1f} GB total ({info['disk_free_gb']:.1f} GB free)
OS: {info['os']}

TIER: {tier.upper()}
ELIGIBLE: {'✓ YES' if eligible else '✗ NO'}
"""
        
        self.hw_text.config(state="normal")
        self.hw_text.delete("1.0", "end")
        self.hw_text.insert("1.0", hw_info)
        self.hw_text.config(state="disabled")
    
    def _refresh_status(self):
        """Atualiza status periodicamente."""
        if self.running:
            state = self.api_client.get_active_host()
            if state.get("active"):
                self._log(f"Active host: {state['host']['name']}")
            else:
                self._log("No active host")
        
        self.after(5000, self._refresh_status)
    
    def _save_settings(self):
        """Salva configurações."""
        self.config.player_name = self.player_name_var.get()
        self.config.api_url = self.api_url_var.get()
        self.config.server_memory_mb = int(self.memory_var.get())
        ConfigManager.save(self.config)
        messagebox.showinfo("Saved", "Settings saved!")
    
    def _download_world(self):
        """Baixa world do storage."""
        self._log("Fetching world state...")
        state = self.api_client.get_world_state()
        
        if not state.get("exists"):
            messagebox.showwarning("Warning", "No world available yet")
            return
        
        # TODO: implementar download real
        self._log(f"World save: {state.get('save_url')}")
    
    def _start_server(self):
        """Inicia servidor e túnel."""
        player_name = self.player_name_var.get()
        
        if not player_name:
            messagebox.showerror("Error", "Please enter a player name")
            return
        
        self._log("Starting server...")
        self.running = True
        self.start_btn.config(state="disabled")
        
        def run():
            # Registra como host
            info = HardwareAnalyzer.get_system_info()
            tier = HardwareAnalyzer.get_tier(info)
            
            self._log(f"Registering as {tier} host...")
            reg = self.api_client.register_host(
                self.config.player_uuid,
                player_name,
                tier,
                "1.20.1"
            )
            
            if "error" in reg:
                self._log(f"Registration failed: {reg['error']}", "ERROR")
                self.running = False
                self.start_btn.config(state="normal")
                return
            
            # Inicia servidor
            self._log("Launching Minecraft server...")
            if not self.server_manager.start_server():
                self._log("Server failed to start", "ERROR")
                self.running = False
                self.start_btn.config(state="normal")
                return
            
            # Inicia túnel
            self._log(f"Starting {self.config.tunnel_service} tunnel...")
            if self.config.tunnel_service == "ngrok":
                self.tunnel_manager = NgrokTunnel(self.config.server_port, self.config.tunnel_token)
            else:
                self.tunnel_manager = CloudflareTunnel(self.config.server_port, self.config.tunnel_token)
            
            if not self.tunnel_manager.start():
                self._log("Tunnel failed to start", "ERROR")
                self.server_manager.stop_server()
                self.running = False
                self.start_btn.config(state="normal")
                return
            
            endpoint = self.tunnel_manager.get_endpoint()
            self._log(f"Tunnel online: {endpoint}")
            
            # Notifica API
            self._log("Notifying API...")
            parts = endpoint.split(":")
            self.api_client.update_tunnel(
                self.config.player_uuid,
                parts[0],
                parts[1] if len(parts) > 1 else "25565"
            )
            
            # Heartbeat
            self._log("Starting heartbeat...")
            self.stop_btn.config(state="normal")
            
            while self.running and self.server_manager.is_running():
                self.api_client.send_heartbeat(self.config.player_uuid)
                time.sleep(30)
            
            # Cleanup
            self._log("Stopping server...")
            self.tunnel_manager.stop()
            self.server_manager.stop_server()
            self.running = False
            self.stop_btn.config(state="disabled")
            self.start_btn.config(state="normal")
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
    
    def _stop_server(self):
        """Para servidor."""
        self.running = False
        self._log("Stopping...")
    
    def _on_closing(self):
        """Encerra aplicação."""
        if self.running:
            if messagebox.askyesno("Warning", "Server is running. Stop it?"):
                self.running = False
                self.server_manager.stop_server()
                if self.tunnel_manager:
                    self.tunnel_manager.stop()
        
        self.destroy()

if __name__ == "__main__":
    app = NomadLauncher()
    app.mainloop()
