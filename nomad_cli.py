#!/usr/bin/env python3
"""
NOMAD SERVER - CLIENT CLI
Ferramenta de linha de comando para testar/gerenciar servidor
"""

import argparse
import requests
import json
import sys
from pathlib import Path
import uuid
from datetime import datetime

API_URL = "http://localhost:5000"
API_KEY = "your-api-key"

class NomadCLI:
    def __init__(self, api_url: str = API_URL, api_key: str = API_KEY):
        self.api_url = api_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})
    
    def _print_json(self, data):
        """Printa JSON formatado."""
        print(json.dumps(data, indent=2, default=str))
    
    # ====== HOST COMMANDS ======
    
    def cmd_host_register(self, name, tier="mid", version="1.20.1"):
        """nomad host register <name> [--tier mid] [--version 1.20.1]"""
        player_uuid = str(uuid.uuid4())
        
        payload = {
            "player_uuid": player_uuid,
            "player_name": name,
            "hardware_tier": tier,
            "version": version
        }
        
        resp = self.session.post(f"{self.api_url}/api/host/register", json=payload)
        
        print(f"✓ Host registered")
        print(f"  UUID: {player_uuid}")
        print(f"  Name: {name}")
        print(f"  Tier: {tier}")
        self._print_json(resp.json())
    
    def cmd_host_update_tunnel(self, player_uuid, public_ip, tunnel_port="25565"):
        """nomad host update-tunnel <uuid> <ip> [--port 25565]"""
        payload = {
            "player_uuid": player_uuid,
            "public_ip": public_ip,
            "tunnel_port": tunnel_port
        }
        
        resp = self.session.post(f"{self.api_url}/api/host/update-tunnel", json=payload)
        
        print(f"✓ Tunnel updated: {public_ip}:{tunnel_port}")
        self._print_json(resp.json())
    
    def cmd_host_heartbeat(self, player_uuid, players_online=0, tps=20):
        """nomad host heartbeat <uuid> [--players 0] [--tps 20]"""
        payload = {
            "player_uuid": player_uuid,
            "players_online": players_online,
            "tps": tps
        }
        
        resp = self.session.post(f"{self.api_url}/api/host/heartbeat", json=payload)
        
        print(f"✓ Heartbeat sent")
        self._print_json(resp.json())
    
    def cmd_host_shutdown(self, player_uuid, save_hash, save_url):
        """nomad host shutdown <uuid> <hash> <url>"""
        payload = {
            "player_uuid": player_uuid,
            "save_file_hash": save_hash,
            "save_file_url": save_url
        }
        
        resp = self.session.post(f"{self.api_url}/api/host/shutdown", json=payload)
        
        print(f"✓ Host shutdown")
        self._print_json(resp.json())
    
    def cmd_host_list(self):
        """nomad host list"""
        resp = self.session.get(f"{self.api_url}/api/state/all-hosts")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"\n✓ Total hosts: {data['total']}\n")
            
            for host in data.get("hosts", []):
                status = "🟢 ACTIVE" if host.get("status") == "active" else "⚪ OFFLINE"
                print(f"  {status} {host.get('player_name')}")
                print(f"    UUID: {host.get('player_uuid')[:8]}...")
                print(f"    Tier: {host.get('hardware_tier')}")
                print(f"    Address: {host.get('full_address')}")
                print()
        else:
            print("✗ Error:", resp.json())
    
    # ====== STATE COMMANDS ======
    
    def cmd_state_active(self):
        """nomad state active"""
        resp = requests.get(f"{self.api_url}/api/state/active-host")
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("active"):
                host = data.get("host")
                print(f"✓ Active host: {host.get('name')}")
                print(f"  Endpoint: {host.get('endpoint')}")
                print(f"  Tier: {host.get('tier')}")
                print(f"  Uptime: {host.get('uptime_minutes'):.1f} minutes")
            else:
                print("ℹ No active host")
        else:
            print("✗ Error:", resp.json())
    
    def cmd_state_world(self):
        """nomad state world"""
        resp = requests.get(f"{self.api_url}/api/state/world")
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("exists"):
                print("✓ World state:")
                print(f"  Host: {data.get('current_host')}")
                print(f"  Last save: {data.get('last_save')}")
                print(f"  Hash: {data.get('save_hash')}")
                print(f"  URL: {data.get('save_url')}")
                print(f"  Players online: {data.get('players_online')}")
            else:
                print("ℹ World not initialized")
        else:
            print("✗ Error:", resp.json())
    
    def cmd_state_health(self):
        """nomad state health"""
        resp = requests.get(f"{self.api_url}/api/health")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ API Status: {data.get('status').upper()}")
            print(f"  Timestamp: {data.get('timestamp')}")
        else:
            print(f"✗ API Error: {resp.status_code}")
    
    # ====== WHITELIST COMMANDS ======
    
    def cmd_whitelist_add(self, player_uuid, player_name):
        """nomad whitelist add <uuid> <name>"""
        payload = {
            "player_uuid": player_uuid,
            "player_name": player_name
        }
        
        resp = self.session.post(f"{self.api_url}/api/whitelist/add", json=payload)
        
        if resp.status_code == 201:
            print(f"✓ Player whitelisted: {player_name}")
        else:
            print("✗ Error:", resp.json())
    
    def cmd_whitelist_check(self, player_uuid):
        """nomad whitelist check <uuid>"""
        resp = requests.get(f"{self.api_url}/api/whitelist/check/{player_uuid}")
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("whitelisted"):
                print(f"✓ Whitelisted: {data.get('player_name')}")
            else:
                print("✗ Not whitelisted")
        else:
            print("✗ Error:", resp.json())
    
    # ====== AUDIT COMMANDS ======
    
    def cmd_audit_log(self, limit=20):
        """nomad audit log [--limit 20]"""
        resp = self.session.get(f"{self.api_url}/api/audit-log")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"\n✓ Recent actions (limit {limit}):\n")
            
            for log in data.get("logs", [])[:limit]:
                print(f"  [{log.get('timestamp')}] {log.get('action')}")
                print(f"    Player: {log.get('player_uuid')[:8]}...")
                print(f"    Details: {log.get('details')}")
                print()
        else:
            print("✗ Error:", resp.json())

def main():
    parser = argparse.ArgumentParser(
        description="Nomad Server CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nomad host register "Player1" --tier high
  nomad host list
  nomad state active
  nomad state world
  nomad whitelist add <uuid> "Player2"
  nomad audit log --limit 50
        """
    )
    
    parser.add_argument("--api-url", default=API_URL, help="API URL")
    parser.add_argument("--api-key", default=API_KEY, help="API Key")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # HOST COMMANDS
    host_parser = subparsers.add_parser("host", help="Host management")
    host_sub = host_parser.add_subparsers(dest="host_cmd")
    
    register = host_sub.add_parser("register")
    register.add_argument("name", help="Player name")
    register.add_argument("--tier", default="mid", choices=["low", "mid", "high"])
    register.add_argument("--version", default="1.20.1")
    
    tunnel = host_sub.add_parser("update-tunnel")
    tunnel.add_argument("uuid", help="Player UUID")
    tunnel.add_argument("ip", help="Public IP")
    tunnel.add_argument("--port", default="25565")
    
    hb = host_sub.add_parser("heartbeat")
    hb.add_argument("uuid", help="Player UUID")
    hb.add_argument("--players", type=int, default=0)
    hb.add_argument("--tps", type=float, default=20)
    
    shutdown = host_sub.add_parser("shutdown")
    shutdown.add_argument("uuid", help="Player UUID")
    shutdown.add_argument("hash", help="Save file hash")
    shutdown.add_argument("url", help="Save file URL")
    
    host_sub.add_parser("list")
    
    # STATE COMMANDS
    state_parser = subparsers.add_parser("state", help="Query state")
    state_sub = state_parser.add_subparsers(dest="state_cmd")
    state_sub.add_parser("active")
    state_sub.add_parser("world")
    state_sub.add_parser("health")
    
    # WHITELIST COMMANDS
    wl_parser = subparsers.add_parser("whitelist", help="Whitelist management")
    wl_sub = wl_parser.add_subparsers(dest="wl_cmd")
    
    wl_add = wl_sub.add_parser("add")
    wl_add.add_argument("uuid")
    wl_add.add_argument("name")
    
    wl_check = wl_sub.add_parser("check")
    wl_check.add_argument("uuid")
    
    # AUDIT COMMANDS
    audit_parser = subparsers.add_parser("audit", help="Audit log")
    audit_sub = audit_parser.add_subparsers(dest="audit_cmd")
    log_cmd = audit_sub.add_parser("log")
    log_cmd.add_argument("--limit", type=int, default=20)
    
    args = parser.parse_args()
    
    cli = NomadCLI(args.api_url, args.api_key)
    
    try:
        if args.command == "host":
            if args.host_cmd == "register":
                cli.cmd_host_register(args.name, args.tier, args.version)
            elif args.host_cmd == "update-tunnel":
                cli.cmd_host_update_tunnel(args.uuid, args.ip, args.port)
            elif args.host_cmd == "heartbeat":
                cli.cmd_host_heartbeat(args.uuid, args.players, args.tps)
            elif args.host_cmd == "shutdown":
                cli.cmd_host_shutdown(args.uuid, args.hash, args.url)
            elif args.host_cmd == "list":
                cli.cmd_host_list()
        
        elif args.command == "state":
            if args.state_cmd == "active":
                cli.cmd_state_active()
            elif args.state_cmd == "world":
                cli.cmd_state_world()
            elif args.state_cmd == "health":
                cli.cmd_state_health()
        
        elif args.command == "whitelist":
            if args.wl_cmd == "add":
                cli.cmd_whitelist_add(args.uuid, args.name)
            elif args.wl_cmd == "check":
                cli.cmd_whitelist_check(args.uuid)
        
        elif args.command == "audit":
            if args.audit_cmd == "log":
                cli.cmd_audit_log(args.limit)
        
        else:
            parser.print_help()
    
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
