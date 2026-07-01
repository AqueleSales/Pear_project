"""
PEAR PROJECT - LAUNCHER DESKTOP (PySide6)
Suporte Multi-Perfil, Correção de Threads e Shutdown Seguro.
"""
import os
from dotenv import load_dotenv
import sys
import psutil
import platform
import logging
import requests
import subprocess
import asyncio
from pyngrok import ngrok
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextEdit, QGroupBox, QMessageBox, QComboBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from world_manager import WorldManager, StorageConfig

# Configuração de Log
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============================================================================
# LÓGICA DE HARDWARE
# ============================================================================
class HardwareAnalyzer:
    @staticmethod
    def get_system_info():
        return {
            "cpu_cores": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_total_gb": psutil.virtual_memory().total / (1024**3),
            "ram_available_gb": psutil.virtual_memory().available / (1024**3),
            "os": platform.system(),
        }

    @staticmethod
    def get_tier(info):
        ram = info["ram_total_gb"]
        cores = info["cpu_cores"]
        if ram >= 16 and cores >= 8: return "high"
        if ram >= 8 and cores >= 4: return "mid"
        return "low"

# ============================================================================
# THREADS (Lógica do Servidor e Perfis)
# ============================================================================
class ServerRunnerThread(QThread):
    log_signal = Signal(str)
    status_signal = Signal(bool)

    def __init__(self, api_url, api_key, player_name, profile_folder):
        super().__init__()
        self.api_url = api_url
        self.api_key = api_key
        self.player_name = player_name
        self.profile_folder = profile_folder
        self.is_running = True
        self.server_process = None
        self.public_ip = None
        self.tunnel_port = None

        self.profile_dir = os.path.abspath(os.path.join("perfis", self.profile_folder))
        os.makedirs(self.profile_dir, exist_ok=True)

        self.storage_config = StorageConfig(
            backend="local",
            api_url=self.api_url,
            api_key=self.api_key,
            local_storage_path="./pear_storage_nuvem"
        )
        self.world_mgr = WorldManager(self.storage_config, world_dir=self.profile_dir)

    def run(self):
        self.log_signal.emit(f"Preparando Perfil: {self.profile_folder.upper()}")
        self.log_signal.emit("Analisando Hardware...")

        hw_info = HardwareAnalyzer.get_system_info()
        tier = HardwareAnalyzer.get_tier(hw_info)
        headers = {"X-API-Key": self.api_key}
        player_uuid = "mock-uuid-1234"

        # 1. Registra Host
        payload = {
            "player_uuid": player_uuid,
            "player_name": self.player_name,
            "hardware_tier": tier,
            "version": f"26.1-{self.profile_folder}"
        }

        try:
            resp = requests.post(f"{self.api_url}/api/host/register", json=payload, headers=headers, timeout=5)
            if resp.status_code in [200, 201]:
                self.log_signal.emit("✅ Host registrado na Nuvem!")
            else:
                self.log_signal.emit(f"❌ Erro na API: {resp.text}")
                self.status_signal.emit(False)
                return
        except Exception as e:
            self.log_signal.emit(f"❌ Falha de conexão: {e}")
            self.status_signal.emit(False)
            return

        # 2. Check de Mapa
        self.log_signal.emit("Verificando se há mapas salvos na nuvem para este perfil...")
        try:
            state_resp = requests.get(f"{self.api_url}/api/state/world").json()
            if state_resp.get("exists") and state_resp.get("save_url"):
                self.log_signal.emit("Baixando mapa...")
                asyncio.run(self.world_mgr.download_world_async(state_resp["save_url"]))
            else:
                self.log_signal.emit("Nenhum mapa encontrado. Gerando novo mundo...")
        except Exception as e:
            self.log_signal.emit(f"Aviso ao checar mundo: {e}")

        # 3. Boot do Servidor Java
        server_jar_path = os.path.join(self.profile_dir, "server.jar")
        if not os.path.exists(server_jar_path):
            self.log_signal.emit(f"❌ ERRO: O arquivo 'server.jar' não foi encontrado na pasta: {self.profile_dir}")
            self.status_signal.emit(False)
            return

        with open(os.path.join(self.profile_dir, "eula.txt"), "w") as f:
            f.write("eula=true\n")

        self.log_signal.emit(f"Iniciando Servidor Java a partir de: {self.profile_dir}")
        self.server_process = subprocess.Popen(
            ["java", "-Xmx4096M", "-Xms4096M", "-jar", "server.jar", "nogui"],
            cwd=self.profile_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # 4. Ngrok Tunnel
        self.log_signal.emit("Abrindo Túnel TCP...")
        try:
            # ==============================================================
            # COLOQUE O SEU TOKEN DO NGROK AQUI EMBAIXO
            # ==============================================================
            ngrok_token = os.getenv("NGROK_TOKEN")
            ngrok.set_auth_token(ngrok_token)

            tunnel = ngrok.connect(25565, "tcp")
            public_url = tunnel.public_url.replace("tcp://", "")
            self.public_ip, self.tunnel_port = public_url.split(":")
            self.log_signal.emit(f"🔗 IP do Servidor: {self.public_ip}:{self.tunnel_port}")

            tunnel_payload = {
                "player_uuid": player_uuid,
                "public_ip": self.public_ip,
                "tunnel_port": self.tunnel_port
            }
            requests.post(f"{self.api_url}/api/host/update-tunnel", json=tunnel_payload, headers=headers)
        except Exception as e:
            self.log_signal.emit(f"❌ Erro Ngrok: {e}")
            self.status_signal.emit(False)
            return

        self.log_signal.emit("🚀 SERVIDOR ONLINE! Pode conectar.")
        self.status_signal.emit(True)

        # Loop de Heartbeat Inteligente (Não trava mais a thread!)
        while self.is_running and self.server_process.poll() is None:
            try:
                requests.post(f"{self.api_url}/api/host/heartbeat",
                              json={"player_uuid": player_uuid, "players_online": 0, "tps": 20.0},
                              headers=headers, timeout=3)
            except:
                pass

            # Pica o sono de 30s em pedacinhos de 1 segundo para responder ao botão de Parar imediatamente
            for _ in range(30):
                if not self.is_running:
                    break
                QThread.sleep(1)

        # ==============================================================
        # LÓGICA DE SHUTDOWN (Agora roda no Background, sem congelar a UI)
        # ==============================================================
        self.log_signal.emit("Desligando o servidor Java em segurança...")

        if self.server_process:
            try:
                self.server_process.stdin.write("stop\n")
                self.server_process.stdin.flush()
                self.server_process.wait(timeout=15)
            except:
                self.server_process.kill()

        self.log_signal.emit("Fechando túnel Ngrok...")
        ngrok.kill()

        self.log_signal.emit("Compactando mundo para upload... Aguarde.")
        upload_result = asyncio.run(self.world_mgr.upload_world_async("world"))

        if upload_result.get("status") == "success":
            self.log_signal.emit(f"✅ Mundo salvo na nuvem! ({upload_result.get('size_mb', 0):.2f} MB)")
            try:
                requests.post(f"{self.api_url}/api/host/shutdown",
                              json={"player_uuid": "mock-uuid-1234",
                                    "save_file_hash": upload_result["file_hash"],
                                    "save_file_url": upload_result["url"]},
                              headers={"X-API-Key": self.api_key})
            except:
                pass
        else:
            self.log_signal.emit(f"❌ Erro no upload: {upload_result.get('error')}")

        self.log_signal.emit("✅ Concluído. O servidor foi totalmente encerrado.")
        self.status_signal.emit(False) # Avisa a UI que terminamos


    def stop(self):
        # O botão da UI apenas aciona essa flag agora, sem travar o PC!
        self.is_running = False


# ============================================================================
# INTERFACE GRÁFICA (UI)
# ============================================================================
class PearLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pear Project - Server Launcher")
        self.setFixedSize(700, 520)

        # Estilos globais atualizados para lidar com o botão disabled dinamicamente
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; color: #cdd6f4; }
            QGroupBox { border: 2px solid #313244; border-radius: 8px; margin-top: 10px; font-weight: bold; color: #89b4fa; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QLabel { color: #cdd6f4; font-size: 13px; }
            QLineEdit, QComboBox { background-color: #181825; border: 1px solid #45475a; border-radius: 4px; padding: 5px; color: #cdd6f4; }
            QPushButton { background-color: #89b4fa; color: #11111b; border-radius: 4px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #45475a; color: #6c7086; }
            
            QPushButton#btn_stop { background-color: #f38ba8; color: #11111b; }
            QPushButton#btn_stop:hover { background-color: #eba0ac; }
            QPushButton#btn_stop:disabled { background-color: #45475a; color: #6c7086; }
            
            QTextEdit { background-color: #11111b; border: 1px solid #45475a; color: #a6e3a1; font-family: Consolas; padding: 5px; }
        """)

        self.server_thread = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        title = QLabel("🍐 PEAR PROJECT")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        config_group = QGroupBox("Configurações do Jogador")
        config_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nickname:"))
        self.input_name = QLineEdit("Player1")
        row1.addWidget(self.input_name)
        row1.addWidget(QLabel("API URL:"))
        self.input_api = QLineEdit("http://localhost:5000")
        row1.addWidget(self.input_api)
        config_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Modo de Jogo:"))
        self.profile_combo = QComboBox()
        self.profiles = {
            "Vanilla Optimizada (PaperMC)": "vanilla",
            "Servidor com Mods (Fabric)": "fabric"
        }
        self.profile_combo.addItems(list(self.profiles.keys()))
        row2.addWidget(self.profile_combo)
        config_layout.addLayout(row2)

        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        main_layout.addWidget(self.console)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ INICIAR SERVIDOR")
        self.btn_start.clicked.connect(self.start_server)

        self.btn_stop = QPushButton("⏹ PARAR SERVIDOR")
        self.btn_stop.setObjectName("btn_stop") # Atribui o ID para o CSS colorir certo
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_server)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        main_layout.addLayout(btn_layout)

    def log(self, message):
        self.console.append(message)

    def start_server(self):
        player_name = self.input_name.text().strip()
        if not player_name:
            QMessageBox.warning(self, "Aviso", "O Nickname não pode ficar vazio!")
            return

        self.btn_start.setEnabled(False)
        self.input_name.setEnabled(False)
        self.input_api.setEnabled(False)
        self.profile_combo.setEnabled(False)
        self.console.clear()

        selected_profile_folder = self.profiles[self.profile_combo.currentText()]

        self.server_thread = ServerRunnerThread(
            api_url=self.input_api.text().strip(),
            api_key="your-secret-key-here-change-in-production",
            player_name=player_name,
            profile_folder=selected_profile_folder
        )
        self.server_thread.log_signal.connect(self.log)
        self.server_thread.status_signal.connect(self.on_server_status_changed)
        self.server_thread.start()

    def on_server_status_changed(self, is_online):
        if is_online:
            self.btn_stop.setEnabled(True)
        else:
            self.reset_ui()

    def stop_server(self):
        # Desativa o botão instantaneamente para evitar múltiplos cliques
        self.btn_stop.setEnabled(False)
        self.log("Iniciando processo de desligamento... Aguarde.")

        if self.server_thread and self.server_thread.isRunning():
            self.server_thread.stop() # Apenas passa a flag, o código de fundo faz o resto!

    def reset_ui(self):
        self.btn_start.setEnabled(True)
        self.input_name.setEnabled(True)
        self.input_api.setEnabled(True)
        self.profile_combo.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PearLauncher()
    window.show()
    sys.exit(app.exec())