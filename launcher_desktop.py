"""
PEAR PROJECT - SUPER LAUNCHER V1.8 (PySide6)
Nível Produção: Detecção de Processo via pgrep, SSH KeepAlive, Validação de Secrets e Edição Nativa de TOML
"""
import os
from dotenv import load_dotenv
import sys
import time
import socket
import threading
import logging
import subprocess
import uuid
import shlex
import paramiko
import re
import minecraft_launcher_lib
from pyngrok import ngrok
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextEdit, QGroupBox, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configurações da Oracle e Proxy
ORACLE_IP = "163.176.54.0"
SSH_USER = "ubuntu"
SSH_KEY_PATH = os.path.abspath("ssh-key-2026-07-02.key")
PROXY_SERVER_NAME = "nomad-backend" # <-- AQUI ESTAVA O PROBLEMA! Corrigido para o nome real.

# ============================================================================
# GERENCIADOR DA ORACLE (PARAMIKO SSH - KEEPALIVE)
# ============================================================================
class OracleManager:
    def __init__(self, log_signal):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.log_signal = log_signal

    def connect(self):
        self.log_signal.emit("☁️ Conectando à Oracle via Paramiko SSH...")
        self.client.connect(
            hostname=ORACLE_IP,
            username=SSH_USER,
            port=22,
            key_filename=SSH_KEY_PATH,
            timeout=15
        )
        # Previne que a conexão SSH morra por inatividade
        self.client.get_transport().set_keepalive(30)

    def execute_command_with_status(self, command):
        """Executa um comando remotamente e retorna (stdout, stderr, exit_status)."""
        _, stdout, stderr = self.client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        return stdout.read().decode('utf-8', errors='ignore').strip(), stderr.read().decode('utf-8', errors='ignore').strip(), exit_status

    def sync_forwarding_secret(self, local_profile_dir):
        """Garante que o local e a nuvem usem o mesmo forwarding.secret (Parity Check)."""
        local_secret_path = os.path.join(local_profile_dir, "forwarding.secret")
        if os.path.exists(local_secret_path):
            self.log_signal.emit("🔐 Sincronizando forwarding.secret local com a Oracle...")
            try:
                with open(local_secret_path, 'r') as f:
                    secret = f.read().strip()

                safe_secret = shlex.quote(secret)
                cmd = f"echo {safe_secret} > ~/velocity/forwarding.secret"
                _, _, status = self.execute_command_with_status(cmd)

                if status == 0:
                    self.log_signal.emit("✅ Segredos sincronizados perfeitamente!")
                else:
                    self.log_signal.emit("⚠️ Falha ao escrever secret remoto.")
            except Exception as e:
                self.log_signal.emit(f"⚠️ Erro ao ler secret local: {e}")
        else:
            self.log_signal.emit("ℹ️ Não encontrei forwarding.secret local (Ignorando paridade rígida).")

    def prepare_and_update(self, ip, port):
        # 1. Verifica existência
        _, _, status = self.execute_command_with_status("test -f ~/velocity/velocity.toml")
        if status != 0:
            self.log_signal.emit("❌ Erro Crítico: ~/velocity/velocity.toml não encontrado.")
            return False

        # 2. Atualiza arquivo via Python nativo na Oracle (Substitui o sed frágil)
        self.log_signal.emit(f"📝 Injetando IP e Modo Offline via parser Python remoto ({ip}:{port})...")

        # O Script Python é passado de forma isolada, e os valores via sys.argv.
        # Isso impede QUALQUER conflito de aspas (shlex) com Expressões Regulares.
        python_injector = """
import re, sys
try:
    server_name = sys.argv[1]
    ip_port = sys.argv[2]
    with open('velocity.toml', 'r', encoding='utf-8') as f:
        data = f.read()
    
    # Regex escaping acontece nativamente dentro do Python remoto
    pattern = r'(?m)^(\\s*' + re.escape(server_name) + r'\\s*=\\s*)(["\\']).*?(["\\'])'
    
    if not re.search(pattern, data):
        print('CHAVE_NAO_ENCONTRADA')
        print('--- DIAGNÓSTICO: Chaves disponíveis no arquivo ---')
        for line in data.splitlines():
            if '=' in line and not line.strip().startswith('#'):
                print(line.strip()[:80])
        sys.exit(1)
        
    new_data = re.sub(pattern, r'\\g<1>\\g<2>' + ip_port + r'\\g<3>', data)
    
    # FIX AUTENTICAÇÃO: Força o Velocity a aceitar jogadores offline/piratas e desliga verificação de chave
    new_data = re.sub(r'(?m)^(\\s*online-mode\\s*=\\s*)(true|false)', r'\\g<1>false', new_data)
    new_data = re.sub(r'(?m)^(\\s*force-key-authentication\\s*=\\s*)(true|false)', r'\\g<1>false', new_data)
    
    with open('velocity.toml', 'w', encoding='utf-8') as f:
        f.write(new_data)
    print('SUCESSO')
except Exception as e:
    print(f"ERRO_PYTHON: {e}")
    sys.exit(2)
"""
        cmd_update = f"cd ~/velocity && python3 -c {shlex.quote(python_injector)} {shlex.quote(PROXY_SERVER_NAME)} {shlex.quote(f'{ip}:{port}')}"
        stdout, stderr, status = self.execute_command_with_status(cmd_update)

        if status != 0 or stdout.splitlines()[0] != 'SUCESSO':
            self.log_signal.emit(f"❌ Falha ao injetar TOML! Retorno:")
            # Se falhou, exibe todo o output do script para o usuário descobrir a chave certa
            for line in stdout.splitlines():
                self.log_signal.emit(f"   {line}")
            if stderr:
                self.log_signal.emit(f"   Erros: {stderr}")
            return False

        self.log_signal.emit("✅ TOML atualizado com segurança algorítmica e autenticação corrigida!")
        return True

    def restart_process(self):
        # 1. Mata qualquer instância antiga via pgrep/pkill (NUNCA via velocity.pid,
        #    que é escrito por um subshell/canal SSH efêmero e não reflete o PID real do Java)
        self.log_signal.emit("💀 Desligando Velocity (via pgrep/pkill)...")
        kill_script = """
        cd ~/velocity
        pkill -f velocity.jar 2>/dev/null
        for i in $(seq 1 20); do
            pgrep -f velocity.jar > /dev/null 2>&1 || break
            sleep 1
        done
        pkill -9 -f velocity.jar 2>/dev/null
        exit 0
        """
        self.execute_command_with_status(kill_script)
        self.log_signal.emit("✅ Processo antigo erradicado da memória.")

        # 2. Inicia o Java em background. Sem echo $! / velocity.pid: esse valor nunca
        #    é confiável quando capturado via exec_command + nohup + shell efêmero.
        self.log_signal.emit("🔄 Dando boot no Java...")
        cmd_restart = (
            "cd ~/velocity && "
            "rm -f velocity.log && "
            "nohup java -jar velocity.jar > velocity.log 2>&1 </dev/null &"
        )
        self.client.exec_command(cmd_restart)
        time.sleep(2)  # dá tempo do processo aparecer na tabela de processos remota

        # 3. Confirmação rápida via pgrep (existência do processo, não PID file)
        self.log_signal.emit("⏳ Verificando se o processo Java subiu...")
        booted = False
        for _ in range(10):
            _, _, status = self.execute_command_with_status("pgrep -f velocity.jar > /dev/null 2>&1")
            if status == 0:
                booted = True
                break
            time.sleep(1)

        if not booted:
            self.log_signal.emit("❌ Erro Fatal: nenhum processo velocity.jar encontrado depois do boot.")
            self.log_signal.emit("🔍 Coletando rastros da falha no velocity.log...")
            log, _, _ = self.execute_command_with_status("tail -n 100 ~/velocity/velocity.log 2>/dev/null")
            if log.strip():
                self.log_signal.emit("===== VELOCITY.LOG =====")
                self.log_signal.emit(log)
                self.log_signal.emit("========================")
            else:
                self.log_signal.emit("⚠️ O velocity.log está vazio. Tente rodar 'cd ~/velocity && java -jar velocity.jar' manualmente na Oracle.")
            return False

        self.log_signal.emit("✅ Processo Java encontrado. Aguardando boot completo do Velocity...")
        return True

    def is_velocity_running(self):
        """Retorna True se existir um processo velocity.jar rodando (via pgrep, sem depender de PID file)."""
        _, _, status = self.execute_command_with_status("pgrep -f velocity.jar > /dev/null 2>&1")
        return status == 0

    def wait_for_velocity(self, timeout=60):
        self.log_signal.emit("⏳ Lendo logs da Oracle (tail -n 100) para confirmar inicialização plena...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.is_velocity_running():
                self.log_signal.emit("❌ Erro Fatal: O processo Java (Velocity) MORREU súbitamente.")
                log, _, _ = self.execute_command_with_status("tail -n 30 ~/velocity/velocity.log 2>/dev/null")
                if log: self.log_signal.emit(f"📝 Último suspiro:\n{log}")
                return False

            # Lê apenas as últimas 100 linhas (Otimização de tráfego)
            log_content, _, _ = self.execute_command_with_status("tail -n 100 ~/velocity/velocity.log 2>/dev/null")
            lower_log = log_content.lower()

            if "address already in use" in lower_log:
                self.log_signal.emit("❌ Erro Crítico: Porta já em uso.")
                return False
            if "forwarding secret invalid" in lower_log or "invalid secret" in lower_log:
                self.log_signal.emit("❌ Erro Crítico: Forwarding Secret inválido/incompatível.")
                return False
            if "exception in thread \"main\"" in lower_log:
                self.log_signal.emit("❌ Erro Crítico: Crash fatal na thread principal do Java.")
                return False

            if "done (" in lower_log or "listening on " in lower_log:
                self.log_signal.emit("✅ SUCESSO! Proxy Velocity carregado e pronto.")
                return True

            time.sleep(2)

        self.log_signal.emit("❌ Timeout: Processo travado no boot (>60s).")
        return False

    def stop_velocity(self):
        self.log_signal.emit("☁️ Enviando sinal de Shutdown para a Oracle...")
        self.execute_command_with_status("pkill -f velocity.jar 2>/dev/null")

    def close(self):
        if self.client:
            self.client.close()

# ============================================================================
# THREAD DO CLIENTE (O JOGO MINECRAFT)
# ============================================================================
class MinecraftClientThread(QThread):
    log_signal = Signal(str)

    def __init__(self, player_name):
        super().__init__()
        self.player_name = player_name
        self.version = "26.1.2"
        self.mc_dir = os.path.abspath("./pear_minecraft_client")

    def run(self):
        self.log_signal.emit(f"🎮 Iniciando o cliente Minecraft para: {self.player_name}")
        self.log_signal.emit("⏳ Verificando arquivos da Mojang...")
        try:
            minecraft_launcher_lib.install.install_minecraft_version(self.version, self.mc_dir)
            options = {"username": self.player_name, "uuid": str(uuid.uuid4()), "token": ""}
            cmd = minecraft_launcher_lib.command.get_minecraft_command(self.version, self.mc_dir, options)
            cmd.extend(["--quickPlayMultiplayer", f"{ORACLE_IP}:25565"])
            self.log_signal.emit("🚀 Tudo pronto! Jogo sendo aberto.")
            subprocess.Popen(cmd)
        except Exception as e:
            self.log_signal.emit(f"❌ Erro ao abrir o Minecraft: {e}")

# ============================================================================
# THREAD DO SERVIDOR (HOST / NGROK / ORACLE)
# ============================================================================
class ServerRunnerThread(QThread):
    log_signal = Signal(str)
    status_signal = Signal(bool)

    def __init__(self, player_name, profile_folder="vanilla"):
        super().__init__()
        self.player_name = player_name
        self.is_running = True
        self.server_process = None
        self.tunnel = None
        self.oracle = None
        self.profile_dir = os.path.abspath(os.path.join("perfis", profile_folder))
        os.makedirs(self.profile_dir, exist_ok=True)

    def enforce_local_paper_configs(self):
        """Força online-mode=false no servidor local para evitar conflitos de autenticação"""
        server_props = os.path.join(self.profile_dir, "server.properties")
        if os.path.exists(server_props):
            self.log_signal.emit("🛠️ Auto-Configurando server.properties (online-mode=false)...")
            with open(server_props, 'r') as f:
                data = f.read()
            data = re.sub(r'(?m)^online-mode=.*', 'online-mode=false', data)
            with open(server_props, 'w') as f:
                f.write(data)

    def is_local_port_in_use(self, port):
        """Verifica de forma silenciosa e rápida se uma porta está sendo usada (Processo Zumbi)"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex(('127.0.0.1', port)) == 0

    def wait_for_local_port(self, ip, port, timeout=60):
        start_time = time.time()
        while time.time() - start_time < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex((ip, port)) == 0:
                    return True
            time.sleep(1)
        return False

    def run(self):
        # Validação Prévia (Fail Fast 1) - Checa Jar
        jar_path = os.path.join(self.profile_dir, "server.jar")
        if not os.path.exists(jar_path):
            self.log_signal.emit(f"❌ Arquivo ausente: '{jar_path}'.")
            self.status_signal.emit(False)
            return

        # Validação Prévia (Fail Fast 2) - Sistema Anti-Zumbi (Previne java.io.IOException)
        self.log_signal.emit("🔍 Checando estado da porta local...")
        if self.is_local_port_in_use(25565):
            self.log_signal.emit("❌ ERRO FATAL: A porta 25565 já está em uso no seu PC!")
            self.log_signal.emit("⚠️ Isso significa que um servidor Java antigo não foi fechado corretamente e ficou travando os arquivos do mundo (DirectoryLock).")
            self.log_signal.emit("🔧 SOLUÇÃO: Abra o Gerenciador de Tarefas do Windows e finalize todas as tarefas com nome 'Java'. Depois tente novamente.")
            self.status_signal.emit(False)
            return

        # Aplica a correção do ChatGPT no Paper local
        self.enforce_local_paper_configs()

        self.log_signal.emit("⚙️ Ligando PaperMC (Backend)...")
        self.server_process = subprocess.Popen(
            ["java", "-Xmx4G", "-Xms4G", "-Djline.terminal=jline.UnsupportedTerminal", "-jar", "server.jar", "nogui", "--nojline"],
            cwd=self.profile_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        def read_paper_logs(process, signal):
            for line in iter(process.stdout.readline, ''):
                if line: signal.emit(f"[PAPER] {line.strip()}")
            process.stdout.close()

        threading.Thread(target=read_paper_logs, args=(self.server_process, self.log_signal), daemon=True).start()

        self.log_signal.emit("⏳ Aguardando porta local (25565)...")
        if not self.wait_for_local_port("127.0.0.1", 25565, timeout=120):
            self.log_signal.emit("❌ Timeout local.")
            self.status_signal.emit(False)
            return

        self.log_signal.emit("🔗 Abrindo Túnel Ngrok...")
        try:
            ngrok_token = os.getenv("NGROK_TOKEN")
            if ngrok_token: ngrok.set_auth_token(ngrok_token)
            self.tunnel = ngrok.connect(25565, "tcp")
            public_ip, tunnel_port = self.tunnel.public_url.replace("tcp://", "").split(":")
            self.log_signal.emit(f"✅ Túnel Aberto ({public_ip}:{tunnel_port})!")

            self.oracle = OracleManager(self.log_signal)
            self.oracle.connect()
            self.oracle.sync_forwarding_secret(self.profile_dir)

            if not self.oracle.prepare_and_update(public_ip, tunnel_port):
                raise Exception("Falha na Injeção TOML")
            if not self.oracle.restart_process():
                raise Exception("Falha no boot do Velocity")
            if not self.oracle.wait_for_velocity(timeout=60):
                raise Exception("Falha nos logs do Velocity")

            self.log_signal.emit("🎯 ORQUESTRAÇÃO 100% BLINDADA CONCLUÍDA!")
            self.status_signal.emit(True)

        except Exception as e:
            self.log_signal.emit(f"❌ Abortando: {e}")
            if self.oracle: self.oracle.close()
            self.status_signal.emit(False)
            return

        # Duplo Monitoramento de Vida (Paper e Velocity)
        while self.is_running and self.server_process.poll() is None:
            if not self.oracle.is_velocity_running():
                self.log_signal.emit("🚨 ALERTA: A nuvem Oracle (Velocity) caiu!")
                break
            QThread.sleep(5)

        self.shutdown_routine()

    def shutdown_routine(self):
        self.log_signal.emit("Desligando infraestrutura...")

        # 1. Desliga Oracle
        if self.oracle:
            try:
                self.oracle.stop_velocity()
                self.oracle.close()
            except: pass

        # 2. Desliga Paper
        if self.server_process and self.server_process.poll() is None:
            try:
                self.server_process.stdin.write("stop\n")
                self.server_process.stdin.flush()
                self.server_process.wait(timeout=10)
            except: self.server_process.kill()

        # 3. Limpeza Profunda Ngrok
        if self.tunnel:
            ngrok.disconnect(self.tunnel.public_url)
        ngrok.kill()

        self.log_signal.emit("✅ Desligamento limpo concluído.")
        self.status_signal.emit(False)

    def stop(self):
        self.is_running = False

# ============================================================================
# INTERFACE GRÁFICA (UI)
# ============================================================================
class PearLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pear Project - Super Launcher V1.8")
        self.setFixedSize(700, 550)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; color: #cdd6f4; }
            QGroupBox { border: 2px solid #313244; border-radius: 8px; margin-top: 10px; font-weight: bold; color: #89b4fa; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QLabel { color: #cdd6f4; font-size: 13px; }
            QLineEdit { background-color: #181825; border: 1px solid #45475a; border-radius: 4px; padding: 5px; color: #cdd6f4; }
            QPushButton { border-radius: 4px; padding: 10px; font-weight: bold; font-size: 14px; }
            QPushButton:disabled { background-color: #45475a; color: #6c7086; }
            QPushButton#btn_host_play { background-color: #f5c2e7; color: #11111b; }
            QPushButton#btn_host_play:hover { background-color: #cba6f7; }
            QPushButton#btn_play_only { background-color: #a6e3a1; color: #11111b; }
            QPushButton#btn_play_only:hover { background-color: #94e2d5; }
            QPushButton#btn_stop { background-color: #f38ba8; color: #11111b; }
            QPushButton#btn_stop:hover { background-color: #eba0ac; }
            QTextEdit { background-color: #11111b; border: 1px solid #45475a; color: #a6e3a1; font-family: Consolas; padding: 5px; }
        """)

        self.auto_start_client = False
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        title = QLabel("🍐 PEAR LAUNCHER V1.8")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        config_group = QGroupBox("Identificação")
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("Seu Nickname:"))
        self.input_name = QLineEdit("Player1")
        config_layout.addWidget(self.input_name)
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        action_layout = QHBoxLayout()
        self.btn_host_play = QPushButton("🚀 HOSPEDAR E JOGAR")
        self.btn_host_play.setObjectName("btn_host_play")
        self.btn_host_play.clicked.connect(self.host_and_play)

        self.btn_play_only = QPushButton("🎮 APENAS CONECTAR")
        self.btn_play_only.setObjectName("btn_play_only")
        self.btn_play_only.clicked.connect(self.play_only)

        action_layout.addWidget(self.btn_host_play)
        action_layout.addWidget(self.btn_play_only)
        main_layout.addLayout(action_layout)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        main_layout.addWidget(self.console)

        self.btn_stop = QPushButton("⏹ PARAR HOSPEDAGEM")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_server)
        main_layout.addWidget(self.btn_stop)

    def log(self, message):
        self.console.append(message)
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def host_and_play(self):
        if not self.input_name.text().strip(): return QMessageBox.warning(self, "Aviso", "Nickname vazio!")
        self.auto_start_client = True
        self.start_server()

    def play_only(self):
        if not self.input_name.text().strip(): return QMessageBox.warning(self, "Aviso", "Nickname vazio!")
        self.auto_start_client = False
        self.btn_play_only.setEnabled(False)
        self.btn_host_play.setEnabled(False)
        self.launch_game()

    def launch_game(self):
        self.mc_thread = MinecraftClientThread(player_name=self.input_name.text().strip())
        self.mc_thread.log_signal.connect(self.log)
        self.mc_thread.finished.connect(self.on_game_closed)
        self.mc_thread.start()

    def on_game_closed(self):
        self.btn_play_only.setEnabled(True)
        if not hasattr(self, 'server_thread') or not self.server_thread.isRunning():
            self.btn_host_play.setEnabled(True)

    def start_server(self):
        self.btn_host_play.setEnabled(False)
        self.btn_play_only.setEnabled(False)
        self.console.clear()
        self.server_thread = ServerRunnerThread(player_name=self.input_name.text().strip())
        self.server_thread.log_signal.connect(self.log)
        self.server_thread.status_signal.connect(self.on_server_status_changed)
        self.server_thread.start()

    def on_server_status_changed(self, is_online):
        if is_online:
            self.btn_stop.setEnabled(True)
            self.btn_play_only.setEnabled(True)
            if self.auto_start_client:
                self.launch_game()
                self.auto_start_client = False
        else:
            self.btn_stop.setEnabled(False)
            self.btn_host_play.setEnabled(True)
            self.btn_play_only.setEnabled(True)

    def stop_server(self):
        self.btn_stop.setEnabled(False)
        self.log("Solicitando parada de todos os sistemas...")
        if hasattr(self, 'server_thread') and self.server_thread.isRunning():
            self.server_thread.stop()

# ============================================================================
# SETUP WIZARD (ASSISTENTE DE PRIMEIRA VIAGEM)
# ============================================================================
from PySide6.QtWidgets import QDialog, QFileDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, \
    QMessageBox
import shutil


class SetupWizard(QDialog):
    """Janela que abre apenas na primeira vez para configurar chaves secretas."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pear Launcher - Configuração Inicial")
        self.setFixedSize(500, 200)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; font-weight: bold; }
            QLabel { color: #cdd6f4; font-size: 13px; }
            QLineEdit { background-color: #181825; border: 1px solid #45475a; border-radius: 4px; padding: 5px; color: #cdd6f4; }
            QPushButton { background-color: #cba6f7; color: #11111b; border-radius: 4px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #b4befe; }
        """)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("🔑 Token do Ngrok (Authtoken):"))
        self.input_ngrok = QLineEdit()
        layout.addWidget(self.input_ngrok)

        layout.addWidget(QLabel("🔒 Arquivo da Chave SSH da Oracle (.key):"))
        key_layout = QHBoxLayout()
        self.input_key = QLineEdit()
        self.input_key.setReadOnly(True)
        self.btn_browse = QPushButton("Procurar...")
        self.btn_browse.clicked.connect(self.browse_key)
        key_layout.addWidget(self.input_key)
        key_layout.addWidget(self.btn_browse)
        layout.addLayout(key_layout)

        self.btn_save = QPushButton("Salvar e Iniciar Launcher")
        self.btn_save.clicked.connect(self.save_config)
        layout.addWidget(self.btn_save)

    def browse_key(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecione a chave SSH", "",
                                                   "Key Files (*.key);;All Files (*)")
        if file_path:
            self.input_key.setText(file_path)

    def save_config(self):
        ngrok_token = self.input_ngrok.text().strip()
        key_path = self.input_key.text().strip()

        if not ngrok_token or not key_path:
            QMessageBox.warning(self, "Erro", "Preencha o Token e selecione a Chave SSH!")
            return

        # 1. Cria o arquivo .env
        with open(".env", "w") as f:
            f.write(f"NGROK_TOKEN={ngrok_token}\n")

        # 2. Copia a chave SSH para a pasta raiz do Launcher
        target_key_path = os.path.join(os.getcwd(), "ssh-key-2026-07-02.key")
        if key_path != target_key_path:
            shutil.copy(key_path, target_key_path)

        QMessageBox.information(self, "Sucesso", "Configuração salva! O Launcher vai iniciar agora.")
        self.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Sistema inteligente para detectar a primeira viagem
    needs_setup = False
    if not os.path.exists(".env") or not os.path.exists("ssh-key-2026-07-02.key"):
        needs_setup = True

    if needs_setup:
        wizard = SetupWizard()
        if wizard.exec() != QDialog.Accepted:
            sys.exit()  # Se o cara fechar o wizard sem salvar, o programa encerra.

        # Recarrega as variáveis de ambiente agora que o .env foi criado
        load_dotenv()

    window = PearLauncher()
    window.show()
    sys.exit(app.exec())