"""
PEAR PROJECT - SUPER LAUNCHER V5.3 (PySide6)
Nível Produção: Frameless Premium UI, Switches Nativos, Microsoft OAuth
"""
import os
import json
import requests
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
import zipfile
import base64
import minecraft_launcher_lib
from pyngrok import ngrok, conf
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextEdit, QMessageBox, QTabWidget, QFileDialog, QDialog,
                               QSystemTrayIcon, QMenu, QCheckBox)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QIcon, QAction, QPainter, QColor, QPen

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configurações da Oracle e Proxy
ORACLE_IP = "163.176.54.0"
SSH_USER = "ubuntu"
SSH_KEY_PATH = os.path.abspath("ssh-key-2026-07-02.key")
PROXY_SERVER_NAME = "nomad-backend"

# ============================================================================
# DESIGN: ÍCONE DA PERA, SWITCHES E STYLESHEET
# ============================================================================
def create_pear_icon():
    """Gera um ícone de Pera desenhado matematicamente."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Cabinho da Pera (Marrom)
    painter.setPen(QPen(QColor("#78350f"), 4, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(32, 16, 38, 8)

    # Folhinha (Verde Escuro)
    painter.setBrush(QColor("#22c55e"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(36, 10, 14, 8)

    # Corpo da Pera (Verde)
    painter.setBrush(QColor("#84cc16"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(22, 20, 20, 20) # Topo
    painter.drawEllipse(14, 30, 36, 28) # Base

    painter.end()
    return QIcon(pixmap)

class ToggleSwitch(QWidget):
    """Interruptor customizado idêntico ao do iOS / Discord"""
    toggled = Signal(bool)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = False

    def isChecked(self):
        return self._checked

    def setChecked(self, val):
        self._checked = val
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Cores de Fundo
        bg_color = QColor("#3b82f6") if self._checked else QColor("#334155")
        thumb_pos = self.width() - 22 if self._checked else 2

        # Fundo da Pílula
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        # Botãozinho Branco
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(thumb_pos, 2, 20, 20)
        painter.end()

STYLESHEET = """
    /* Main Window: Controla o fundo geral e os cantos arredondados perfeitos */
    QWidget#main_window { background-color: #0B0F19; border: 1px solid #1e293b; border-radius: 12px; }
    QDialog, QMainWindow { background-color: transparent; color: #f8fafc; font-family: 'Segoe UI', Arial; }
    
    QLabel { font-size: 14px; font-weight: bold; color: #cbd5e1; }
    
    /* Inputs agora têm altura mínima e margens confortáveis (nada espremido) */
    QLineEdit { background-color: #111827; border: 2px solid #1e293b; border-radius: 8px; padding: 8px; color: #f8fafc; font-size: 14px; min-height: 20px; }
    QLineEdit:focus { border: 2px solid #3b82f6; }
    
    QPushButton { border-radius: 8px; padding: 5px; font-weight: bold; font-size: 14px; border: none; color: white; min-height: 25px; }
    QPushButton:pressed { padding-top: 10px; padding-bottom: 6px; } /* Animação tátil corrigida para não sumir o texto */
    QPushButton:disabled { background-color: #1e293b; color: #475569; }
    
    QPushButton#btn_primary { background-color: #3b82f6; color: white; }
    QPushButton#btn_primary:hover { background-color: #2563eb; }
    
    QPushButton#btn_secondary { background-color: #10b981; color: white; }
    QPushButton#btn_secondary:hover { background-color: #059669; }
    
    QPushButton#btn_danger { background-color: #ef4444; color: white; }
    QPushButton#btn_danger:hover { background-color: #dc2626; }
    
    QPushButton#btn_warning { background-color: #f97316; color: white; }
    QPushButton#btn_warning:hover { background-color: #ea580c; }
    
    QPushButton#btn_link { background-color: transparent; color: #93c5fd; padding: 0; font-weight: normal; min-height: 20px; }
    QPushButton#btn_link:hover { color: #60a5fa; text-decoration: underline; }
    
    /* Abas Estilo VS Code / Navegador */
    QTabWidget::pane { border: none; background: transparent; }
    QTabBar::tab { background: transparent; color: #64748b; padding: 12px 24px; font-weight: bold; border-bottom: 3px solid transparent; }
    QTabBar::tab:selected { color: #3b82f6; border-bottom: 3px solid #3b82f6; }
    QTabBar::tab:hover:!selected { color: #cbd5e1; background: #1e293b; border-radius: 8px; }
    
    QTextEdit { background-color: #06090F; border: 1px solid #1e293b; border-radius: 8px; color: #10b981; font-family: Consolas; padding: 12px; font-size: 13px; }
    
    /* Checkbox de Lembrar de Mim (Quadrado Moderno Gordinho) */
    QCheckBox { font-weight: bold; color: #cbd5e1; spacing: 12px; }
    QCheckBox::indicator { width: 22px; height: 22px; border-radius: 6px; border: 2px solid #334155; background-color: #111827; }
    QCheckBox::indicator:hover { border: 2px solid #3b82f6; }
    QCheckBox::indicator:checked { background-color: #3b82f6; border: 2px solid #3b82f6; }
"""

# ============================================================================
# COMPONENTE: BARRA DE TÍTULO CUSTOMIZADA (FRAMELESS)
# ============================================================================
class CustomTitleBar(QWidget):
    def __init__(self, parent, title_text):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(45)
        self.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)

        icon_label = QLabel()
        icon_label.setPixmap(create_pear_icon().pixmap(24, 24))
        layout.addWidget(icon_label)

        title = QLabel(title_text)
        title.setStyleSheet("color: #cbd5e1; font-weight: bold; font-size: 14px; letter-spacing: 1px;")
        layout.addWidget(title)
        layout.addStretch()

        btn_min = QPushButton("—")
        btn_min.setFixedSize(35, 35)
        btn_min.setStyleSheet("QPushButton { background: transparent; color: #cbd5e1; padding: 0; font-weight: bold; font-size: 16px; border-radius: 8px; } QPushButton:hover { background: #1e293b; }")
        btn_min.clicked.connect(self.parent.showMinimized)
        layout.addWidget(btn_min)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(35, 35)
        btn_close.setStyleSheet("QPushButton { background: transparent; color: #cbd5e1; padding: 0; font-weight: bold; font-size: 16px; border-radius: 8px; } QPushButton:hover { background: #ef4444; color: white; }")
        btn_close.clicked.connect(self.close_parent)
        layout.addWidget(btn_close)

        self.drag_start_pos = None

    def close_parent(self):
        self.parent.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.drag_start_pos is not None:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            self.parent.move(self.parent.x() + delta.x(), self.parent.y() + delta.y())
            self.drag_start_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None

# ============================================================================
# API MINESKIN E ORACLE MANAGER
# ============================================================================
MINESKIN_API = "https://api.mineskin.org/v2/generate"

def generate_mineskin_texture(image_url, variant="classic"):
    headers = {"User-Agent": "NomadServerLauncher/1.0"}
    payload = {"variant": variant, "visibility": "unlisted", "url": image_url}
    resp = requests.post(MINESKIN_API, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    texture = (data.get("skin", {}).get("texture") or data.get("data", {}).get("texture") or data.get("texture"))
    if not texture or "value" not in texture: raise Exception(f"Resposta inesperada da MineSkin: {data}")
    return texture["value"], texture["signature"]

class OracleManager:
    def __init__(self, log_signal=None):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.log_signal = log_signal

    def emit_log(self, msg):
        if self.log_signal: self.log_signal.emit(msg)

    def connect(self):
        self.client.connect(hostname=ORACLE_IP, username=SSH_USER, port=22, key_filename=SSH_KEY_PATH, timeout=15)
        self.client.get_transport().set_keepalive(30)

    def execute_command_with_status(self, command):
        _, stdout, stderr = self.client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        return stdout.read().decode('utf-8', errors='ignore').strip(), stderr.read().decode('utf-8', errors='ignore').strip(), exit_status

    def upload_world(self, local_zip_path):
        sftp = self.client.open_sftp()
        sftp.put(local_zip_path, '/home/ubuntu/velocity/cloud_save.zip')
        sftp.close()

    def download_world(self, local_zip_path):
        sftp = self.client.open_sftp()
        remote_path = '/home/ubuntu/velocity/cloud_save.zip'
        try:
            sftp.stat(remote_path)
            sftp.get(remote_path, local_zip_path)
            sftp.close()
            return True
        except IOError:
            sftp.close()
            return False

    def manage_user(self, action, user, param=""):
        db_script = """
import json, sys, os, hashlib
db_path = os.path.expanduser('~/velocity/users.json')
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()
if not os.path.exists(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, 'w') as f: json.dump({}, f)
with open(db_path, 'r') as f: db = json.load(f)

action = sys.argv[1]; user = sys.argv[2]; param = sys.argv[3] if len(sys.argv) > 3 else ""

if action == 'register':
    if user in db: print('EXISTS'); sys.exit(1)
    db[user] = {'password': hash_pw(param), 'skin': ''}
    with open(db_path, 'w') as f: json.dump(db, f)
    print('SUCCESS')
elif action == 'login':
    if user not in db: print('NOT_FOUND'); sys.exit(1)
    if db[user]['password'] != hash_pw(param): print('WRONG_PASS'); sys.exit(1)
    print('SUCCESS')
elif action == 'set_skin':
    if user not in db: print('NOT_FOUND'); sys.exit(1)
    db[user]['skin'] = param
    with open(db_path, 'w') as f: json.dump(db, f)
    print('SUCCESS')
elif action == 'get_skin':
    if user not in db: print('NONE'); sys.exit(0)
    print(db[user].get('skin', 'NONE') or 'NONE')
"""
        cmd = f"python3 -c {shlex.quote(db_script)} {shlex.quote(action)} {shlex.quote(user)} {shlex.quote(param)}"
        stdout, _, _ = self.execute_command_with_status(cmd)
        return stdout.strip()

    def upload_skin_file(self, skin_name, value, signature):
        script = """
import os, sys
skins_dir = os.path.expanduser('~/velocity/skins')
os.makedirs(skins_dir, exist_ok=True)
name, value, signature = sys.argv[1], sys.argv[2], sys.argv[3]
with open(os.path.join(skins_dir, name + '.skin'), 'w') as f:
    f.write(value + chr(10) + signature)
print('SUCCESS')
"""
        cmd = f"python3 -c {shlex.quote(script)} {shlex.quote(skin_name)} {shlex.quote(value)} {shlex.quote(signature)}"
        stdout, _, status = self.execute_command_with_status(cmd)
        return status == 0 and 'SUCCESS' in stdout

    def download_all_skin_files(self):
        script = """
import os, json
skins_dir = os.path.expanduser('~/velocity/skins')
result = {}
if os.path.isdir(skins_dir):
    for fname in os.listdir(skins_dir):
        if fname.endswith('.skin'):
            with open(os.path.join(skins_dir, fname), 'r') as f:
                result[fname] = f.read()
print(json.dumps(result))
"""
        cmd = f"python3 -c {shlex.quote(script)}"
        stdout, _, _ = self.execute_command_with_status(cmd)
        try: return json.loads(stdout.strip() or '{}')
        except Exception: return {}

    def sync_forwarding_secret(self, local_profile_dir):
        local_secret_path = os.path.join(local_profile_dir, "forwarding.secret")
        if not os.path.exists(local_secret_path):
            with open(local_secret_path, 'w') as f: f.write(uuid.uuid4().hex + uuid.uuid4().hex)
        try:
            with open(local_secret_path, 'r') as f: secret = f.read().strip()
            self.execute_command_with_status(f"echo {shlex.quote(secret)} > ~/velocity/forwarding.secret")
        except Exception: pass

    def prepare_and_update(self, ip, port):
        _, _, status = self.execute_command_with_status("test -f ~/velocity/velocity.toml")
        if status != 0: return False
        python_injector = """
import re, sys
try:
    server_name = sys.argv[1]; ip_port = sys.argv[2]
    with open('velocity.toml', 'r', encoding='utf-8') as f: data = f.read()
    pattern = r'(?m)^(\\s*' + re.escape(server_name) + r'\\s*=\\s*)(["\\']).*?(["\\'])'
    if not re.search(pattern, data): print('CHAVE_NAO_ENCONTRADA'); sys.exit(1)
    new_data = re.sub(pattern, r'\\g<1>\\g<2>' + ip_port + r'\\g<3>', data)
    new_data = re.sub(r'(?m)^(\\s*online-mode\\s*=\\s*)(true|false)', r'\\g<1>false', new_data)
    new_data = re.sub(r'(?m)^(\\s*force-key-authentication\\s*=\\s*)(true|false)', r'\\g<1>false', new_data)
    new_data = re.sub(r'(?m)^(\\s*player-info-forwarding-mode\\s*=\\s*)(["\\']).*?(["\\'])', r'\\g<1>\\g<2>modern\\g<3>', new_data)
    with open('velocity.toml', 'w', encoding='utf-8') as f: f.write(new_data)
    print('SUCESSO')
except Exception as e:
    print(f"ERRO_PYTHON: {e}"); sys.exit(2)
"""
        cmd_update = f"cd ~/velocity && python3 -c {shlex.quote(python_injector)} {shlex.quote(PROXY_SERVER_NAME)} {shlex.quote(f'{ip}:{port}')}"
        stdout, _, status = self.execute_command_with_status(cmd_update)
        return status == 0 and stdout.splitlines()[0] == 'SUCESSO'

    def restart_process(self):
        kill_script = """
        cd ~/velocity
        pkill -f velocity.jar 2>/dev/null
        for i in $(seq 1 20); do pgrep -f velocity.jar > /dev/null 2>&1 || break; sleep 1; done
        pkill -9 -f velocity.jar 2>/dev/null
        exit 0
        """
        self.execute_command_with_status(kill_script)
        self.client.exec_command("cd ~/velocity && rm -f velocity.log && nohup java -jar velocity.jar > velocity.log 2>&1 </dev/null &")
        time.sleep(2)
        return True

    def is_velocity_running(self):
        _, _, status = self.execute_command_with_status("pgrep -f velocity.jar > /dev/null 2>&1")
        return status == 0

    def wait_for_velocity(self, timeout=60):
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.is_velocity_running(): return False
            log_content, _, _ = self.execute_command_with_status("tail -n 100 ~/velocity/velocity.log 2>/dev/null")
            lower_log = log_content.lower()
            if "address already in use" in lower_log or "forwarding secret invalid" in lower_log or "exception in thread" in lower_log:
                return False
            if "done (" in lower_log or "listening on " in lower_log: return True
            time.sleep(2)
        return False

    def set_host_state(self, is_hosting, username="", ip_port=""):
        if is_hosting:
            self.execute_command_with_status(f"echo {shlex.quote(username + '|' + ip_port)} > ~/velocity/current_host.txt")
        else:
            self.execute_command_with_status(f"rm -f ~/velocity/current_host.txt")

    def get_host_state(self):
        stdout, _, status = self.execute_command_with_status("cat ~/velocity/current_host.txt 2>/dev/null")
        if status == 0 and '|' in stdout:
            parts = stdout.strip().split('|')
            return parts[0], parts[1]
        return None, None

    def close(self):
        if self.client: self.client.close()

# ============================================================================
# THREADS DE TRABALHO
# ============================================================================
class CheckOracleThread(QThread):
    result = Signal(bool, str)

    def run(self):
        try:
            oracle = OracleManager()
            oracle.connect()
            host_user, ip_port = oracle.get_host_state()

            if host_user and ip_port and "Iniciando" not in ip_port:
                try:
                    ip, port = ip_port.split(":")
                    with socket.create_connection((ip, int(port)), timeout=3): pass
                    self.result.emit(True, host_user)
                except Exception:
                    oracle.set_host_state(False)
                    self.result.emit(False, "")
            elif host_user and "Iniciando" in ip_port:
                self.result.emit(True, host_user)
            else:
                self.result.emit(False, "")
            oracle.close()
        except Exception:
            self.result.emit(False, "")

class MicrosoftAuthWorker(QThread):
    prompt_signal = Signal(str, str)
    success_signal = Signal(str, str, str, str)
    error_signal = Signal(str)

    def run(self):
        try:
            client_id = "c36a9fb6-4f2a-41ff-90bd-ae7cc92031eb"
            resp = requests.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode", data={
                "client_id": client_id,
                "scope": "XboxLive.signin offline_access"
            }).json()

            if "error" in resp: raise Exception(resp.get('error_description', resp.get('error')))
            url = resp.get('verification_uri') or resp.get('verification_url')
            if not url or not resp.get('user_code'): raise Exception("Resposta inválida da Microsoft")

            self.prompt_signal.emit(url, resp['user_code'])
            device_code = resp['device_code']
            interval = resp.get('interval', 5)
            access_token = None

            while True:
                time.sleep(interval)
                poll_resp = requests.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id,
                    "device_code": device_code
                }).json()

                if "access_token" in poll_resp:
                    access_token = poll_resp["access_token"]
                    break
                if poll_resp.get("error") != "authorization_pending":
                    raise Exception(poll_resp.get("error_description", "Erro na autorização do navegador."))

            xbl_resp = requests.post("https://user.auth.xboxlive.com/user/authenticate", json={
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": f"d={access_token}"},
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            }).json()
            xbl_token = xbl_resp['Token']

            xsts_resp = requests.post("https://xsts.auth.xboxlive.com/xsts/authorize", json={
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT"
            }).json()
            if "err" in xsts_resp: raise Exception("Conta sem perfil Xbox ou menor de idade.")
            xsts_token = xsts_resp['Token']
            uhs = xsts_resp['DisplayClaims']['xui'][0]['uhs']

            mc_resp = requests.post("https://api.minecraftservices.com/authentication/login_with_xbox", json={
                "identityToken": f"XBL3.0 x={uhs};{xsts_token}"
            }).json()
            mc_token = mc_resp['access_token']

            profile = requests.get("https://api.minecraftservices.com/minecraft/profile", headers={
                "Authorization": f"Bearer {mc_token}"
            }).json()
            if "error" in profile: raise Exception("Conta não possui Minecraft Original (Java Edition).")

            username = profile['name']
            uuid_str = profile['id']
            skin_url = profile['skins'][0].get('url', '') if profile.get('skins') else ""

            self.success_signal.emit(username, uuid_str, mc_token, skin_url)
        except Exception as e:
            self.error_signal.emit(str(e))

class AuthWorker(QThread):
    result_signal = Signal(str, str)
    def __init__(self, action, username, password=""):
        super().__init__()
        self.action = action
        self.username = username
        self.password = password
    def run(self):
        try:
            oracle = OracleManager()
            oracle.connect()
            res = oracle.manage_user(self.action, self.username, self.password)
            oracle.close()
            self.result_signal.emit(self.action, res)
        except Exception as e: self.result_signal.emit("ERROR", str(e))

class SkinUploadWorker(QThread):
    result_signal = Signal(str, str)
    def __init__(self, file_path, username):
        super().__init__()
        self.file_path = file_path
        self.username = username
    def run(self):
        try:
            with open(self.file_path, 'rb') as f:
                res_img = requests.post("https://catbox.moe/user/api.php", data={"reqtype": "fileupload"}, files={"fileToUpload": f}, timeout=20)
            if res_img.status_code != 200: return self.result_signal.emit("ERROR", f"Falha HTTP {res_img.status_code}")
            skin_value = res_img.text.strip()
            value, signature = generate_mineskin_texture(skin_value)
            oracle = OracleManager()
            oracle.connect()
            oracle.manage_user('set_skin', self.username, skin_value)
            oracle.upload_skin_file(f"nomad_{self.username.lower()}", value, signature)
            oracle.close()
            self.result_signal.emit("SUCCESS", skin_value)
        except Exception as e: self.result_signal.emit("ERROR", str(e))

class SmartMonitorThread(QThread):
    trigger_shutdown = Signal(str)
    def __init__(self):
        super().__init__()
        self.is_running = True
        self.heavy_games = ["valorant", "cs2", "csgo", "leagueoflegends", "gta5", "r5apex", "fortniteclient"]
    def run(self):
        while self.is_running:
            try:
                if sys.platform == "win32":
                    out = subprocess.check_output('tasklist', creationflags=subprocess.CREATE_NO_WINDOW).decode('utf-8', errors='ignore').lower()
                    for game in self.heavy_games:
                        if f"{game}.exe" in out:
                            self.trigger_shutdown.emit(game.upper())
                            self.is_running = False
                            break
            except: pass
            QThread.sleep(15)
    def stop(self): self.is_running = False

# ============================================================================
# DIALOGOS FRAMELESS (LOGIN E MICROSOFT)
# ============================================================================
class MicrosoftLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(450, 300)
        self.success = False

        main_widget = QWidget(self)
        main_widget.setObjectName("main_window")
        main_widget.setFixedSize(450, 300)
        main_widget.setStyleSheet(STYLESHEET)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(CustomTitleBar(self, "Login Microsoft Original"))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(15)

        self.lbl_info = QLabel("Conectando aos servidores da Microsoft...")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setWordWrap(True)
        content_layout.addWidget(self.lbl_info)

        self.lbl_code = QLabel("")
        self.lbl_code.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self.lbl_code.setAlignment(Qt.AlignCenter)
        self.lbl_code.setStyleSheet("color: #3b82f6;")
        content_layout.addWidget(self.lbl_code)

        self.btn_copy = QPushButton("Copiar Código e Abrir Navegador")
        self.btn_copy.setObjectName("btn_primary")
        self.btn_copy.hide()
        self.btn_copy.clicked.connect(self.open_browser)
        content_layout.addWidget(self.btn_copy)

        main_layout.addWidget(content)

        self.worker = MicrosoftAuthWorker()
        self.worker.prompt_signal.connect(self.show_prompt)
        self.worker.success_signal.connect(self.on_success)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def accept(self): pass

    def force_accept(self): super().accept()

    def show_prompt(self, url, code):
        self.auth_url = url
        self.auth_code = code
        self.lbl_info.setText("1. Copie o código abaixo.\n2. O site abrirá no navegador.\n3. Cole o código e aprove.\nO Launcher continuará sozinho.")
        self.lbl_code.setText(code)
        self.btn_copy.show()

    def open_browser(self):
        QApplication.clipboard().setText(self.auth_code)
        import webbrowser
        webbrowser.open(self.auth_url)
        self.btn_copy.setText("Aguardando aprovação do navegador...")
        self.btn_copy.setEnabled(False)

    def on_success(self, username, uuid_str, token, skin_url):
        self.success = True
        self.username, self.uuid, self.token, self.skin_url = username, uuid_str, token, skin_url
        self.force_accept()

    def on_error(self, err):
        QMessageBox.critical(self, "Erro de Autenticação", f"Falha no login:\n{err}")
        self.reject()

class LoginWindow(QDialog):
    login_successful = Signal(str, str, bool, str, str)

    def __init__(self):
        super().__init__()
        self.logged_user = self.logged_skin = self.logged_uuid = self.logged_token = ""
        self.logged_premium = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(450, 480)

        main_widget = QWidget(self)
        main_widget.setObjectName("main_window")
        main_widget.setFixedSize(450, 480)
        main_widget.setStyleSheet(STYLESHEET)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(CustomTitleBar(self, "Pear Launcher - Login"))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(35, 30, 35, 35)
        content_layout.setSpacing(15)

        title = QLabel("<div style='text-align: center;'><span style='color: #f8fafc; font-weight: 900; font-size: 24px; letter-spacing: 2px;'>PEAR </span><span style='color: #3b82f6; font-weight: 900; font-size: 24px;'>LAUNCHER</span></div>")
        content_layout.addWidget(title)
        content_layout.addSpacing(10)

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Seu Nickname do Jogo")
        self.input_user.returnPressed.connect(self.do_login)
        content_layout.addWidget(self.input_user)

        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("Sua Senha")
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.returnPressed.connect(self.do_login)
        content_layout.addWidget(self.input_pass)

        self.check_remember = QCheckBox("Lembrar meu perfil (Auto-Login)")
        content_layout.addWidget(self.check_remember)

        self.btn_login = QPushButton("Entrar no Servidor (Offline)")
        self.btn_login.setObjectName("btn_secondary")
        self.btn_login.clicked.connect(self.do_login)
        content_layout.addWidget(self.btn_login)

        self.btn_microsoft = QPushButton("Entrar com Conta Original")
        self.btn_microsoft.setObjectName("btn_primary")
        self.btn_microsoft.clicked.connect(self.do_microsoft_login)
        content_layout.addWidget(self.btn_microsoft)

        content_layout.addStretch()
        self.btn_register = QPushButton("Primeira vez aqui? Crie seu perfil grátis!")
        self.btn_register.setObjectName("btn_link")
        self.btn_register.clicked.connect(self.open_register)
        content_layout.addWidget(self.btn_register)

        main_layout.addWidget(content)
        self.check_auto_login()

    def accept(self): pass

    def force_accept(self):
        super().accept()

    def check_auto_login(self):
        if os.path.exists("launcher_settings.json"):
            try:
                with open("launcher_settings.json", "r") as f: data = json.load(f)

                if data.get("is_microsoft") and data.get("ms_token"):
                    self.logged_user = data.get("ms_username")
                    self.logged_uuid = data.get("ms_uuid")
                    self.logged_token = data.get("ms_token")
                    self.logged_skin = data.get("ms_skin", "")
                    self.logged_premium = True
                    QTimer.singleShot(300, self.emit_success_and_accept)
                    return

                saved_user = data.get("saved_user", "")
                saved_pass = data.get("saved_pass", "")
                if saved_user and saved_pass:
                    self.input_user.setText(saved_user)
                    self.input_pass.setText(base64.b64decode(saved_pass).decode('utf-8'))
                    self.check_remember.setChecked(True)
                    QTimer.singleShot(500, self.do_login)
            except: pass

    def emit_success_and_accept(self):
        self.login_successful.emit(self.logged_user, self.logged_skin, self.logged_premium, self.logged_uuid, self.logged_token)
        self.force_accept()

    def save_credentials(self, is_microsoft=False):
        data = {}
        try:
            with open("launcher_settings.json", "r") as f: data = json.load(f)
        except: pass

        data["is_microsoft"] = is_microsoft
        if is_microsoft:
            data.update({"ms_username": self.logged_user, "ms_uuid": self.logged_uuid, "ms_token": self.logged_token, "ms_skin": self.logged_skin, "saved_user": "", "saved_pass": ""})
        else:
            data.update({"saved_user": self.input_user.text().strip(), "saved_pass": base64.b64encode(self.input_pass.text().strip().encode('utf-8')).decode('utf-8'), "ms_token": ""})

        with open("launcher_settings.json", "w") as f: json.dump(data, f)

    def do_microsoft_login(self):
        ms_dialog = MicrosoftLoginDialog(self)
        if ms_dialog.exec() == QDialog.Accepted:
            self.logged_user = ms_dialog.username
            self.logged_skin = ms_dialog.skin_url
            self.logged_uuid = ms_dialog.uuid
            self.logged_token = ms_dialog.token
            self.logged_premium = True

            self.save_credentials(is_microsoft=True)
            self.emit_success_and_accept()

    def do_login(self):
        user, pw = self.input_user.text().strip(), self.input_pass.text().strip()
        if not user or not pw: return QMessageBox.warning(self, "Aviso", "Preencha todos os campos!")

        self.btn_login.setText("Autenticando..."); self.btn_login.setEnabled(False)

        if self.check_remember.isChecked():
            self.save_credentials(is_microsoft=False)
        else:
            if os.path.exists("launcher_settings.json"):
                try:
                    with open("launcher_settings.json", "r") as f: data = json.load(f)
                    data["saved_user"] = ""; data["saved_pass"] = ""
                    with open("launcher_settings.json", "w") as f: json.dump(data, f)
                except: pass

        self.worker = AuthWorker('login', user, pw)
        self.worker.result_signal.connect(self.handle_auth_result)
        self.worker.start()

    def handle_auth_result(self, action, res):
        self.btn_login.setText("Entrar no Servidor (Offline)"); self.btn_login.setEnabled(True)

        if action == 'ERROR': QMessageBox.critical(self, "Erro de Rede", f"Falha Oracle:\n{res}")
        elif res == 'NOT_FOUND': QMessageBox.warning(self, "Erro", "Usuário não existe. Cadastre-se!")
        elif res == 'WRONG_PASS': QMessageBox.warning(self, "Erro", "Senha incorreta!")
        elif res == 'SUCCESS':
            self.skin_worker = AuthWorker('get_skin', self.input_user.text().strip())
            self.skin_worker.result_signal.connect(self.handle_skin_result)
            self.skin_worker.start()

    def handle_skin_result(self, action, res):
        self.logged_skin = res if res not in ('NONE', 'ERROR') else ""
        self.logged_user = self.input_user.text().strip()
        self.emit_success_and_accept()

    def open_register(self): RegisterWindow(self).exec()

class RegisterWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(400, 400)

        main_widget = QWidget(self)
        main_widget.setObjectName("main_window")
        main_widget.setFixedSize(400, 400)
        main_widget.setStyleSheet(STYLESHEET)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(CustomTitleBar(self, "Cadastro"))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(15)

        title = QLabel("CRIAR PERFIL")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(title)

        self.input_user = QLineEdit(); self.input_user.setPlaceholderText("Escolha seu Nickname")
        self.input_pass = QLineEdit(); self.input_pass.setPlaceholderText("Crie uma Senha"); self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_conf = QLineEdit(); self.input_conf.setPlaceholderText("Confirme a Senha"); self.input_conf.setEchoMode(QLineEdit.Password)

        content_layout.addWidget(self.input_user); content_layout.addWidget(self.input_pass); content_layout.addWidget(self.input_conf)

        self.btn_reg = QPushButton("Registrar")
        self.btn_reg.setObjectName("btn_secondary")
        self.btn_reg.clicked.connect(self.do_register)
        content_layout.addWidget(self.btn_reg)

        main_layout.addWidget(content)

    def accept(self): pass
    def force_accept(self): super().accept()

    def do_register(self):
        user, pw, conf = self.input_user.text().strip(), self.input_pass.text().strip(), self.input_conf.text().strip()
        if not user or not pw: return
        if pw != conf: return QMessageBox.warning(self, "Aviso", "As senhas não conferem.")

        self.btn_reg.setText("Salvando..."); self.btn_reg.setEnabled(False)
        self.worker = AuthWorker('register', user, pw)
        self.worker.result_signal.connect(self.handle_reg_result)
        self.worker.start()

    def handle_reg_result(self, action, res):
        self.btn_reg.setText("Registrar"); self.btn_reg.setEnabled(True)
        if res == 'SUCCESS': QMessageBox.information(self, "Sucesso", "Criado! Faça o login."); self.force_accept()
        else: QMessageBox.warning(self, "Erro", "Nickname já registrado ou falha.")

class SkinDropLabel(QLabel):
    skin_dropped = Signal(str)
    def __init__(self):
        super().__init__()
        self.setText("Arraste o arquivo .png da sua skin aqui\n(Use skins 64x64 baixadas do NameMC)")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("QLabel { border: 2px dashed #334155; border-radius: 12px; color: #64748b; background-color: #111827; font-size: 14px; font-weight: 600; } QLabel:hover { background-color: #1e293b; border-color: #3b82f6; color: #94a3b8; }")
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e):
        for url in e.mimeData().urls():
            fp = url.toLocalFile()
            if fp.endswith('.png'):
                self.skin_dropped.emit(fp)
                break
    def mousePressEvent(self, e):
        fp, _ = QFileDialog.getOpenFileName(self, "Selecionar Skin", "", "Imagens PNG (*.png)")
        if fp: self.skin_dropped.emit(fp)

# ============================================================================
# COMPONENTES DO JOGO (MINECRAFT + PAPER SERVER)
# ============================================================================
class MinecraftClientThread(QThread):
    log_signal = Signal(str)
    def __init__(self, player_name, is_premium, mc_uuid="", mc_token=""):
        super().__init__()
        self.player_name, self.is_premium, self.mc_uuid, self.mc_token = player_name, is_premium, mc_uuid, mc_token
        self.version = "26.1.2"
        self.mc_dir = os.path.abspath("./pear_minecraft_client")

    def run(self):
        self.log_signal.emit(f"Iniciando o cliente Minecraft para: {self.player_name}")
        try:
            minecraft_launcher_lib.install.install_minecraft_version(self.version, self.mc_dir)
            options = {
                "username": self.player_name,
                "uuid": self.mc_uuid if self.is_premium and self.mc_uuid else str(uuid.uuid4()),
                "token": self.mc_token if self.is_premium else ""
            }
            cmd = minecraft_launcher_lib.command.get_minecraft_command(self.version, self.mc_dir, options)
            cmd.extend(["--quickPlayMultiplayer", f"{ORACLE_IP}:25565"])
            process = subprocess.Popen(cmd)
            process.wait()
        except Exception as e:
            self.log_signal.emit(f"Erro ao abrir o Minecraft: {e}")


class ServerRunnerThread(QThread):
    log_signal = Signal(str)
    status_signal = Signal(bool)
    skin_injection_signal = Signal(str)

    def __init__(self, player_name, skin_url, profile_folder="vanilla"):
        super().__init__()
        self.player_name, self.skin_url = player_name, skin_url
        self.is_running = True
        self.server_process = self.tunnel = self.oracle = None
        self.profile_dir = os.path.abspath(os.path.join("perfis", profile_folder))
        os.makedirs(self.profile_dir, exist_ok=True)
        self.skin_injection_signal.connect(self.inject_skin_command)

    def calculate_intelligent_ram(self):
        try:
            if sys.platform == "win32":
                out = subprocess.check_output("wmic computersystem get totalphysicalmemory", shell=True).decode()
                res = re.findall(r'\d+', out)
                gb = int(res[0]) / (1024 ** 3) if res else 8.0
            else:
                gb = 8.0
        except:
            gb = 8.0
        self.log_signal.emit(f"Hardware: {gb:.1f} GB de RAM total.")
        if gb <= 5.0:
            return "2G"
        elif gb <= 9.0:
            return "3G"
        elif gb <= 13.0:
            return "4G"
        elif gb <= 17.0:
            return "6G"
        else:
            return "8G"

    def inject_skin_command(self, player_name):
        if self.skin_url and self.skin_url != 'NONE' and self.server_process:
            time.sleep(1)
            self.server_process.stdin.write(f"skin nomad_{player_name.lower()} {player_name}\n")
            self.server_process.stdin.flush()

    def sync_skins_from_cloud(self):
        try:
            sync_oracle = OracleManager(self.log_signal)
            sync_oracle.connect()
            skin_files = sync_oracle.download_all_skin_files()
            sync_oracle.close()
            if skin_files:
                local_skins_dir = os.path.join(self.profile_dir, "plugins", "SkinsRestorer", "skins")
                os.makedirs(local_skins_dir, exist_ok=True)
                for fname, content in skin_files.items():
                    with open(os.path.join(local_skins_dir, fname), "w") as f: f.write(content)
        except:
            pass

    def is_local_port_in_use(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex(('127.0.0.1', port)) == 0

    def wait_for_local_port(self, ip, port, timeout=60):
        start_time = time.time()
        while time.time() - start_time < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex((ip, port)) == 0: return True
            time.sleep(1)
        return False

    def run(self):
        jar_path = os.path.join(self.profile_dir, "server.jar")
        if not os.path.exists(jar_path) or self.is_local_port_in_use(25565):
            self.status_signal.emit(False);
            return

        server_props = os.path.join(self.profile_dir, "server.properties")
        if os.path.exists(server_props):
            with open(server_props, 'r') as f: data = f.read()
            with open(server_props, 'w') as f: f.write(re.sub(r'(?m)^online-mode=.*', 'online-mode=false', data))

        self.sync_skins_from_cloud()
        self.log_signal.emit("Verificando Save P2P na Nuvem...")
        try:
            local_zip = os.path.join(self.profile_dir, "cloud_save.zip")
            sync_oracle = OracleManager(self.log_signal)
            sync_oracle.connect()
            sync_oracle.set_host_state(True, self.player_name, "Iniciando...")
            if sync_oracle.download_world(local_zip):
                self.log_signal.emit("Mundo extraído com sucesso.")
                with zipfile.ZipFile(local_zip, 'r') as zip_ref: zip_ref.extractall(self.profile_dir)
                os.remove(local_zip)
            sync_oracle.close()
        except:
            pass

        # Otimizações de RAM e Aikar's Flags Injetadas Aqui
        ram = self.calculate_intelligent_ram()

        aikar_flags = [
            "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
            "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch",
            "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
            "-XX:G1ReservePercent=20", "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
            "-XX:InitiatingHeapOccupancyPercent=15", "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
            "-XX:MaxTenuringThreshold=1", "-Dusing.aikars.flags=https://mcflags.emc.gs", "-Daikars.new.flags=true"
        ]

        comando_java = ["java", f"-Xmx{ram}", f"-Xms{ram}"] + aikar_flags + [
            "-Djline.terminal=jline.UnsupportedTerminal", "-jar", "server.jar", "nogui", "--nojline"]

        self.server_process = subprocess.Popen(
            comando_java,
            cwd=self.profile_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        server_ready_event = threading.Event()

        def read_paper_logs(process, signal, injection_signal, ready_event):
            for line in iter(process.stdout.readline, ''):
                if line:
                    clean_line = line.strip()
                    signal.emit(f"[PAPER] {clean_line}")
                    if "logged in with entity id" in clean_line or "joined the game" in clean_line:
                        if self.player_name in clean_line.split(): injection_signal.emit(self.player_name)
                    if "Done (" in clean_line or 'For help, type "help"' in clean_line:
                        ready_event.set()
            process.stdout.close()

        threading.Thread(target=read_paper_logs,
                         args=(self.server_process, self.log_signal, self.skin_injection_signal, server_ready_event),
                         daemon=True).start()

        if not self.wait_for_local_port("127.0.0.1", 25565, timeout=120): self.status_signal.emit(False); return

        try:
            # Ngrok Forçado para a Região América do Sul (sa)
            ngrok.set_auth_token(os.getenv("NGROK_TOKEN"))
            config_sa = conf.PyngrokConfig(region="sa")
            self.tunnel = ngrok.connect(25565, "tcp", pyngrok_config=config_sa)
            public_ip, tunnel_port = self.tunnel.public_url.replace("tcp://", "").split(":")

            self.oracle = OracleManager(self.log_signal)
            self.oracle.connect()
            self.oracle.sync_forwarding_secret(self.profile_dir)

            self.log_signal.emit("Avisando a API da Nuvem sobre o novo túnel...")
            api_payload = {
                "player_uuid": self.player_name,
                "public_ip": public_ip,
                "tunnel_port": tunnel_port
            }
            api_resp = requests.post(
                f"http://{ORACLE_IP}:5000/api/host/update-tunnel",
                json=api_payload,
                headers={"X-API-Key": "minecraftpear2026"},
                timeout=20
            )

            if api_resp.status_code != 200:
                raise Exception(f"Erro na API ({api_resp.status_code}): {api_resp.text}")

            if not self.oracle.wait_for_velocity(timeout=60): raise Exception("Falha Logs Velocity")

            self.log_signal.emit("Aguardando o mapa carregar até 100%...")
            server_ready_event.wait(timeout=240)
            if not self.is_running: return

            self.log_signal.emit("Servidor pronto!")
            self.status_signal.emit(True)
        except Exception as e:
            self.log_signal.emit(f"Abortando: {e}")
            if self.oracle: self.oracle.close()
            self.status_signal.emit(False)
            return

        while self.is_running and self.server_process.poll() is None:
            if not self.oracle.is_velocity_running():
                self.log_signal.emit("Nuvem caiu!")
                break
            QThread.sleep(5)

        self.shutdown_routine()

    def shutdown_routine(self):
        self.log_signal.emit("Desligando...")
        if self.server_process and self.server_process.poll() is None:
            try:
                self.server_process.stdin.write("stop\n")
                self.server_process.stdin.flush()
                self.server_process.wait(timeout=30)
            except:
                self.server_process.kill()

        try:
            local_zip = os.path.join(self.profile_dir, "cloud_save.zip")
            with zipfile.ZipFile(local_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for folder in ['world', 'world_nether', 'world_the_end']:
                    folder_path = os.path.join(self.profile_dir, folder)
                    if os.path.exists(folder_path):
                        for root, dirs, files in os.walk(folder_path):
                            for file in files: zipf.write(os.path.join(root, file),
                                                          os.path.relpath(os.path.join(root, file), self.profile_dir))

            sync_oracle = OracleManager(self.log_signal)
            sync_oracle.connect()
            sync_oracle.upload_world(local_zip)
            sync_oracle.set_host_state(False)
            sync_oracle.close()
            self.log_signal.emit("Backup P2P concluído.")
        except:
            pass

        if self.oracle:
            try:
                self.oracle.close()
            except:
                pass
        if self.tunnel: ngrok.disconnect(self.tunnel.public_url)
        ngrok.kill()
        self.status_signal.emit(False)

    def stop(self):
        self.is_running = False

# ============================================================================
# MAIN LAUNCHER UI
# ============================================================================
class PearLauncher(QMainWindow):
    def __init__(self, username, skin_url, is_premium, ghost_mode=False, allow_hosting=True, mc_uuid="", mc_token=""):
        super().__init__()
        self.username, self.skin_url, self.is_premium, self.ghost_mode, self.allow_hosting = username, skin_url, is_premium, ghost_mode, allow_hosting
        self.mc_uuid, self.mc_token = mc_uuid, mc_token
        self.is_force_quitting = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(750, 600)

        icon = create_pear_icon()
        self.setWindowIcon(icon)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(icon)
        self.tray_menu = QMenu()
        show_action = QAction("Abrir Painel", self); show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Sair Totalmente", self); quit_action.triggered.connect(self.force_quit)
        self.tray_menu.addAction(show_action); self.tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

        main_widget = QWidget(self)
        main_widget.setObjectName("main_window")
        main_widget.setFixedSize(750, 600)
        main_widget.setStyleSheet(STYLESHEET)

        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(CustomTitleBar(self, f"Pear Launcher - {self.username}"))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)

        self.tabs = QTabWidget()
        self.tab_launcher = QWidget(); self.tab_perfil = QWidget(); self.tab_config = QWidget()
        self.tabs.addTab(self.tab_launcher, "Iniciar Servidor / Jogar")
        self.tabs.addTab(self.tab_perfil, "Skins e Perfil")
        self.tabs.addTab(self.tab_config, "Configurações")
        content_layout.addWidget(self.tabs)

        main_layout.addWidget(content)
        self.setCentralWidget(main_widget)

        self.build_launcher_tab()
        self.build_perfil_tab()
        self.build_config_tab()
        self.smart_monitor = None

        if "--startup" in sys.argv and self.ghost_mode:
            self.hide()
            self.tray_icon.showMessage("Pear Launcher", "Rodando em segundo plano.", QSystemTrayIcon.Information, 3000)
            QTimer.singleShot(1000, self.auto_start_ghost_host)

    def tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        if self.is_force_quitting: event.accept()
        elif self.ghost_mode:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage("Pear Launcher", "Minimizado em segundo plano.", QSystemTrayIcon.Information, 3000)
        else: self.force_quit()

    def force_quit(self):
        self.is_force_quitting = True
        self.tray_icon.hide()
        if hasattr(self, 'server_thread') and self.server_thread.isRunning(): self.stop_server()
        os._exit(0)

    def auto_start_ghost_host(self):
        if not self.allow_hosting: return
        self.check_thread = CheckOracleThread()
        self.check_thread.result.connect(self.handle_ghost_oracle_check)
        self.check_thread.start()

    def handle_ghost_oracle_check(self, has_host, host_name):
        if not has_host:
            self.update_status("host")
            self.start_server()

    def update_status(self, status_type):
        if status_type == "host": self.host_indicator.setText("<span style='color: #10b981; font-size: 16px;'>●</span> Status: Host")
        elif status_type == "guest": self.host_indicator.setText("<span style='color: #3b82f6; font-size: 16px;'>●</span> Status: Convidado")
        else: self.host_indicator.setText("<span style='color: #64748b; font-size: 16px;'>●</span> Status: Offline")

    def build_launcher_tab(self):
        layout = QVBoxLayout(self.tab_launcher)
        layout.setContentsMargins(25, 25, 25, 25)

        info_layout = QHBoxLayout()
        info = QLabel(f"Bem-vindo, <b>{self.username}</b>!")
        self.host_indicator = QLabel()
        self.update_status("offline")

        info_layout.addWidget(info); info_layout.addStretch(); info_layout.addWidget(self.host_indicator)
        layout.addLayout(info_layout)
        layout.addSpacing(10)

        self.btn_jogar = QPushButton("JOGAR")
        self.btn_jogar.setObjectName("btn_primary")
        self.btn_jogar.setStyleSheet("background-color: #3b82f6; color: white; border-radius: 12px; padding: 18px; font-weight: 900; font-size: 18px; letter-spacing: 2px;")
        self.btn_jogar.clicked.connect(self.on_btn_jogar_clicked)
        layout.addWidget(self.btn_jogar)
        layout.addSpacing(15)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

    def build_perfil_tab(self):
        layout = QVBoxLayout(self.tab_perfil)
        layout.setContentsMargins(30, 30, 30, 30)
        self.skin_drop = SkinDropLabel()
        self.skin_drop.skin_dropped.connect(self.load_skin_preview)
        layout.addWidget(self.skin_drop)
        layout.addSpacing(15)
        self.btn_upload = QPushButton("Salvar Skin na Nuvem")
        self.btn_upload.setObjectName("btn_primary")
        self.btn_upload.setEnabled(False)
        self.btn_upload.clicked.connect(self.upload_skin)
        layout.addWidget(self.btn_upload)
        layout.addSpacing(10)
        self.txt_skin_url = QLineEdit()
        self.txt_skin_url.setReadOnly(True)
        self.txt_skin_url.setText(f"Skin Ativa: {self.skin_url}" if self.skin_url else "Nenhuma skin salva.")
        layout.addWidget(self.txt_skin_url)
        layout.addStretch()

    def build_config_tab(self):
        layout = QVBoxLayout(self.tab_config)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        layout.addWidget(QLabel("Token do Ngrok (Authtoken):"))
        self.config_ngrok = QLineEdit()
        self.config_ngrok.setText(os.getenv("NGROK_TOKEN", ""))
        layout.addWidget(self.config_ngrok)

        layout.addWidget(QLabel("Arquivo da Chave SSH da Oracle (.key):"))
        kl = QHBoxLayout()
        self.config_key = QLineEdit()
        self.config_key.setReadOnly(True)
        self.config_key.setText(os.path.abspath("ssh-key-2026-07-02.key"))
        self.btn_browse_config = QPushButton("Procurar")
        self.btn_browse_config.setObjectName("btn_secondary")
        self.btn_browse_config.setFixedSize(100, 48)
        self.btn_browse_config.clicked.connect(lambda: self.config_key.setText(QFileDialog.getOpenFileName(self, "Chave SSH", "", "Key (*.key);;All (*)")[0] or self.config_key.text()))
        kl.addWidget(self.config_key); kl.addWidget(self.btn_browse_config)
        layout.addLayout(kl)

        self.config_allow_host = ToggleSwitch()
        self.config_allow_host.setChecked(self.allow_hosting)
        row1 = QHBoxLayout(); row1.addWidget(self.config_allow_host); row1.addWidget(QLabel("Permitir que meu PC seja usado como Servidor")); row1.addStretch()
        layout.addLayout(row1)

        self.config_ghost = ToggleSwitch()
        self.config_ghost.setChecked(self.ghost_mode)
        row2 = QHBoxLayout(); row2.addWidget(self.config_ghost); row2.addWidget(QLabel("Modo Fantasma (Minimizar para o Relógio)")); row2.addStretch()
        layout.addLayout(row2)

        startup_checked = False
        try:
            with open("launcher_settings.json", "r") as f: startup_checked = json.load(f).get("startup", False)
        except: pass
        self.config_startup = ToggleSwitch()
        self.config_startup.setChecked(startup_checked)
        row3 = QHBoxLayout(); row3.addWidget(self.config_startup); row3.addWidget(QLabel("Iniciar junto com o Windows")); row3.addStretch()
        layout.addLayout(row3)

        self.btn_reset_cloud = QPushButton("Resetar Nuvem")
        self.btn_reset_cloud.setObjectName("btn_warning")
        self.btn_reset_cloud.clicked.connect(self.reset_cloud_state)
        layout.addWidget(self.btn_reset_cloud)

        self.btn_save_config = QPushButton("Salvar Configurações")
        self.btn_save_config.setObjectName("btn_primary")
        self.btn_save_config.clicked.connect(self.save_configs)
        layout.addWidget(self.btn_save_config)

        layout.addStretch()
        buttons_layout = QHBoxLayout()
        self.btn_logout = QPushButton("Sair da Conta")
        self.btn_logout.setObjectName("btn_secondary")
        self.btn_logout.clicked.connect(self.do_logout)

        self.btn_shutdown = QPushButton("Desligar Launcher")
        self.btn_shutdown.setObjectName("btn_danger")
        self.btn_shutdown.clicked.connect(self.force_quit)
        buttons_layout.addWidget(self.btn_logout); buttons_layout.addWidget(self.btn_shutdown)
        layout.addLayout(buttons_layout)

    def on_btn_jogar_clicked(self):
        self.btn_jogar.setEnabled(False)
        self.btn_jogar.setText("Consultando Nuvem...")
        self.check_thread = CheckOracleThread()
        self.check_thread.result.connect(self.handle_jogar_oracle_check)
        self.check_thread.start()

    def handle_jogar_oracle_check(self, has_host, host_name):
        if has_host:
            self.update_status("host" if host_name == self.username else "guest")
            self.btn_jogar.setText("Abrindo Minecraft...")
            self.launch_game()
        else:
            if self.allow_hosting:
                self.update_status("host")
                self.btn_jogar.setText("Iniciando Servidor...")
                self.start_server()
            else:
                self.btn_jogar.setText("JOGAR")
                self.btn_jogar.setEnabled(True)

    def launch_game(self):
        self.mc_thread = MinecraftClientThread(self.username, self.is_premium, self.mc_uuid, self.mc_token)
        self.mc_thread.log_signal.connect(self.log)
        self.mc_thread.finished.connect(self.on_game_closed)
        self.mc_thread.start()

    def on_game_closed(self):
        self.btn_jogar.setEnabled(True)
        self.btn_jogar.setText("JOGAR")

    def start_server(self):
        self.console.clear()
        self.server_thread = ServerRunnerThread(self.username, self.skin_url)
        self.server_thread.log_signal.connect(self.log)
        self.server_thread.status_signal.connect(self.on_status)
        self.server_thread.start()

        self.smart_monitor = SmartMonitorThread()
        self.smart_monitor.trigger_shutdown.connect(self.on_heavy_game_detected)
        self.smart_monitor.start()

    def on_heavy_game_detected(self, game_name):
        self.tray_icon.showMessage("Alocação Inteligente", f"Jogo {game_name} detectado! Desligando para não dar Lag.", QSystemTrayIcon.Warning, 5000)
        self.stop_server()
        self.update_status("offline")

    def on_status(self, on):
        if on:
            self.btn_jogar.setText("Abrindo Minecraft...")
            self.launch_game()
        else: self.update_status("offline")

    def stop_server(self):
        if hasattr(self, 'smart_monitor') and self.smart_monitor: self.smart_monitor.stop()
        if hasattr(self, 'server_thread'): self.server_thread.stop()

    def save_configs(self):
        if not self.config_ngrok.text().strip() or not self.config_key.text().strip(): return
        with open(".env", "w") as f: f.write(f"NGROK_TOKEN={self.config_ngrok.text().strip()}\n")
        settings = {}
        try:
            with open("launcher_settings.json", "r") as f: settings = json.load(f)
        except: pass
        settings["ghost_mode"] = self.config_ghost.isChecked()
        settings["startup"] = self.config_startup.isChecked()
        settings["allow_hosting"] = self.config_allow_host.isChecked()
        with open("launcher_settings.json", "w") as f: json.dump(settings, f)

        if self.config_startup.isChecked() and sys.platform == "win32":
            subprocess.run(['reg', 'add', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', '/v', 'PearLauncher', '/t', 'REG_SZ', '/d', f'"{os.path.abspath(sys.argv[0])}" --startup', '/f'], creationflags=subprocess.CREATE_NO_WINDOW)
        elif not self.config_startup.isChecked() and sys.platform == "win32":
            subprocess.run(['reg', 'delete', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', '/v', 'PearLauncher', '/f'], creationflags=subprocess.CREATE_NO_WINDOW)

        import shutil
        tk = os.path.join(os.getcwd(), "ssh-key-2026-07-02.key")
        try:
            if os.path.abspath(self.config_key.text().strip()) != tk: shutil.copy(self.config_key.text().strip(), tk)
        except shutil.SameFileError: pass

        self.ghost_mode = self.config_ghost.isChecked()
        self.allow_hosting = self.config_allow_host.isChecked()
        if not self.allow_hosting and hasattr(self, 'server_thread') and self.server_thread.isRunning():
            self.stop_server()
            self.update_status("offline")

    def do_logout(self):
        try:
            with open("launcher_settings.json", "r") as f: data = json.load(f)
            data["saved_user"] = data["saved_pass"] = data["ms_token"] = ""
            with open("launcher_settings.json", "w") as f: json.dump(data, f)
        except: pass
        subprocess.Popen([sys.executable] + sys.argv)
        self.force_quit()

    def reset_cloud_state(self):
        try:
            oracle = OracleManager(self.log)
            oracle.connect()
            oracle.set_host_state(False)
            oracle.close()
        except: pass

    def load_skin_preview(self, file_path):
        self.current_skin_path = file_path
        self.skin_drop.setPixmap(QPixmap(file_path).scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.btn_upload.setEnabled(True)

    def upload_skin(self):
        if not self.current_skin_path: return
        self.btn_upload.setText("Salvando..."); self.btn_upload.setEnabled(False)
        self.up_worker = SkinUploadWorker(self.current_skin_path, self.username)
        self.up_worker.result_signal.connect(self.handle_upload_result)
        self.up_worker.start()

    def handle_upload_result(self, status, url):
        self.btn_upload.setEnabled(True)
        if status == "SUCCESS":
            self.skin_url = url
            self.btn_upload.setText("Salvar Skin (atualizar)")
            self.txt_skin_url.setText(f"Nova Skin Ativa: {url}")
        else: self.btn_upload.setText("Tentar Novamente")

    def log(self, msg):
        # Proteção de RAM: Limita o histórico do console a 1000 linhas
        if self.console.document().blockCount() > 1000:
            cursor = self.console.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

        self.console.append(msg)
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

class SetupWizard(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 220)

        main_widget = QWidget(self)
        main_widget.setObjectName("main_window")
        main_widget.setFixedSize(500, 220)
        main_widget.setStyleSheet(STYLESHEET)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(CustomTitleBar(self, "Setup Inicial"))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)

        content_layout.addWidget(QLabel("Token do Ngrok:"))
        self.input_ngrok = QLineEdit()
        content_layout.addWidget(self.input_ngrok)

        content_layout.addWidget(QLabel("Chave SSH (.key):"))
        kl = QHBoxLayout()
        self.input_key = QLineEdit(); self.input_key.setReadOnly(True)
        self.btn_b = QPushButton("Procurar"); self.btn_b.setObjectName("btn_secondary")
        self.btn_b.clicked.connect(lambda: self.input_key.setText(QFileDialog.getOpenFileName(self, "Chave SSH", "", "Key (*.key);;All (*)")[0] or self.input_key.text()))
        kl.addWidget(self.input_key); kl.addWidget(self.btn_b)
        content_layout.addLayout(kl)

        self.btn_s = QPushButton("Salvar e Continuar")
        self.btn_s.setObjectName("btn_primary")
        self.btn_s.clicked.connect(self.save)
        content_layout.addWidget(self.btn_s)

        main_layout.addWidget(content)

    def save(self):
        if not self.input_ngrok.text().strip() or not self.input_key.text().strip(): return
        with open(".env", "w") as f: f.write(f"NGROK_TOKEN={self.input_ngrok.text().strip()}\n")
        import shutil
        tk = os.path.join(os.getcwd(), "ssh-key-2026-07-02.key")
        try:
            if os.path.abspath(self.input_key.text().strip()) != tk: shutil.copy(self.input_key.text().strip(), tk)
        except shutil.SameFileError: pass
        self.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    if not os.path.exists(".env") or not os.path.exists("ssh-key-2026-07-02.key"):
        if SetupWizard().exec() != QDialog.Accepted: sys.exit()

    ghost_mode = allow_hosting = True
    try:
        with open("launcher_settings.json", "r") as f:
            settings = json.load(f)
            ghost_mode, allow_hosting = settings.get("ghost_mode", False), settings.get("allow_hosting", True)
    except: pass

    login = LoginWindow()
    if login.exec() == QDialog.Accepted:
        w = PearLauncher(login.logged_user, login.logged_skin, login.logged_premium, ghost_mode, allow_hosting, login.logged_uuid, login.logged_token)
        if not ("--startup" in sys.argv and ghost_mode): w.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)