#!/bin/bash
# NOMAD SERVER - VPS SETUP SCRIPT
# Instala e configura API + Velocity na nuvem

set -e

echo "=================================================="
echo "NOMAD SERVER - VPS SETUP"
echo "=================================================="

# ============================================================================
# VERIFICAÇÕES
# ============================================================================

if [ "$EUID" -ne 0 ]; then 
    echo "Este script deve ser rodado como root"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "Python 3 não encontrado. Instalando..."
    apt update && apt install -y python3 python3-pip
fi

if ! command -v java &> /dev/null; then
    echo "Java não encontrado. Instalando..."
    apt install -y openjdk-17-jre-headless
fi

# ============================================================================
# DIRETÓRIOS
# ============================================================================

NOMAD_HOME="/opt/nomad"
NOMAD_API="$NOMAD_HOME/api"
NOMAD_DATA="$NOMAD_HOME/data"
NOMAD_LOGS="$NOMAD_HOME/logs"
NOMAD_USER="nomad"

mkdir -p "$NOMAD_HOME" "$NOMAD_API" "$NOMAD_DATA" "$NOMAD_LOGS"

# ============================================================================
# USUÁRIO NOMAD
# ============================================================================

if ! id "$NOMAD_USER" &>/dev/null; then
    echo "Criando usuário $NOMAD_USER..."
    useradd -r -s /bin/bash -d "$NOMAD_HOME" "$NOMAD_USER"
fi

chown -R "$NOMAD_USER:$NOMAD_USER" "$NOMAD_HOME"

# ============================================================================
# PYTHON DEPENDENCIES
# ============================================================================

echo "Instalando dependências Python..."
pip3 install flask flask-cors requests psutil boto3 google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client gunicorn waitress

# ============================================================================
# COPIAR ARQUIVOS
# ============================================================================

echo "Copiando arquivos da API..."
cp nomad_api.py "$NOMAD_API/"
cp world_manager.py "$NOMAD_API/"

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

cat > "$NOMAD_HOME/.env" <<EOF
NOMAD_API_KEY=$(openssl rand -hex 32)
NOMAD_API_URL=http://localhost:5000
NOMAD_DB_PATH=$NOMAD_DATA/nomad_state.db
NOMAD_STORAGE_BACKEND=local
NOMAD_STORAGE_PATH=$NOMAD_DATA/storage

# S3 (opcional)
# AWS_S3_BUCKET=nomad-backups
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY=
# AWS_SECRET_KEY=

# Google Drive (opcional)
# GDRIVE_FOLDER_ID=
# GDRIVE_SERVICE_ACCOUNT=

# Velocity
VELOCITY_RCON_HOST=127.0.0.1
VELOCITY_RCON_PORT=25575
VELOCITY_RCON_PASSWORD=$(openssl rand -hex 16)
EOF

chown "$NOMAD_USER:$NOMAD_USER" "$NOMAD_HOME/.env"
chmod 600 "$NOMAD_HOME/.env"

echo "Arquivo .env criado em $NOMAD_HOME/.env"
echo "GUARDE A API_KEY!"
cat "$NOMAD_HOME/.env" | grep "NOMAD_API_KEY"

# ============================================================================
# SUPERVISORD (mantém API rodando)
# ============================================================================

echo "Configurando supervisord..."
apt install -y supervisor

cat > /etc/supervisor/conf.d/nomad-api.conf <<EOF
[program:nomad-api]
directory=$NOMAD_API
command=gunicorn -w 4 -b 0.0.0.0:5000 nomad_api:app
user=$NOMAD_USER
autostart=true
autorestart=true
stderr_logfile=$NOMAD_LOGS/api.err.log
stdout_logfile=$NOMAD_LOGS/api.out.log
environment=PATH="$NOMAD_HOME/bin"
EOF

systemctl restart supervisor
supervisorctl update

echo "API iniciada via supervisord"

# ============================================================================
# NGINX (reverse proxy + SSL)
# ============================================================================

echo "Configurando nginx..."
apt install -y nginx certbot python3-certbot-nginx

cat > /etc/nginx/sites-available/nomad <<EOF
upstream nomad_api {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://nomad_api;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/nomad /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

echo "Nginx configurado (HTTP apenas, configure SSL depois)"

# ============================================================================
# FIREWALL
# ============================================================================

echo "Configurando firewall..."
ufw --force enable
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw allow 25565/tcp  # Minecraft (TCP)
ufw allow 25575/tcp  # Velocity RCON

# ============================================================================
# MONITORAMENTO
# ============================================================================

mkdir -p "$NOMAD_DATA/backups"

# Cron job para backups diários do banco de dados
cat >> /etc/crontab <<EOF
0 2 * * * $NOMAD_USER cp $NOMAD_DATA/nomad_state.db $NOMAD_DATA/backups/nomad_state_\$(date +\%Y\%m\%d).db.backup
0 3 * * 0 $NOMAD_USER find $NOMAD_DATA/backups -mtime +30 -delete
EOF

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo "=================================================="
echo "SETUP COMPLETO!"
echo "=================================================="
echo ""
echo "Informações importantes:"
echo "  Diretório: $NOMAD_HOME"
echo "  Logs: $NOMAD_LOGS"
echo "  API URL: http://localhost:5000"
echo ""
echo "Próximos passos:"
echo "  1. Configure SSL com: certbot --nginx -d seu-dominio.com"
echo "  2. Baixe Velocity: https://velocitypowered.com/"
echo "  3. Compile o plugin Velocity e coloque em plugins/"
echo "  4. Configure velocity.toml com backend dummy"
echo "  5. Inicie Velocity com: java -jar velocity.jar"
echo ""
echo "Teste a API:"
echo "  curl -H 'X-API-Key: $(grep NOMAD_API_KEY $NOMAD_HOME/.env | cut -d= -f2)' http://localhost:5000/api/health"
echo ""
