"""
NOMAD SERVER - TEST SUITE
Testa API, persistência, launcher, tunelamento
"""

import unittest
import requests
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import uuid

# Imports (assumindo que rodando do diretório raiz)
# from nomad_api import app, db_query, init_db
# from world_manager import WorldManager, StorageConfig
# from launcher_desktop import NomadAPIClient, HardwareAnalyzer

# ============================================================================
# SETUP
# ============================================================================

API_URL = "http://localhost:5000"
API_KEY = "test-key-change-in-production"
TEST_PLAYER_UUID = str(uuid.uuid4())
TEST_PLAYER_NAME = "TestPlayer"

# ============================================================================
# TEST CLASSES
# ============================================================================

class TestNomadAPI(unittest.TestCase):
    """Testa endpoints da API."""
    
    def setUp(self):
        self.base_url = API_URL
        self.headers = {"X-API-Key": API_KEY}
    
    def test_health_check(self):
        """GET /api/health"""
        resp = requests.get(f"{self.base_url}/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
    
    def test_register_host(self):
        """POST /api/host/register"""
        payload = {
            "player_uuid": TEST_PLAYER_UUID,
            "player_name": TEST_PLAYER_NAME,
            "hardware_tier": "high",
            "version": "1.20.1"
        }
        
        resp = requests.post(
            f"{self.base_url}/api/host/register",
            json=payload,
            headers=self.headers
        )
        
        self.assertIn(resp.status_code, [200, 201])
        data = resp.json()
        self.assertEqual(data["status"], "registered")
    
    def test_update_tunnel(self):
        """POST /api/host/update-tunnel"""
        # Precisa de host registrado primeiro
        self.test_register_host()
        
        payload = {
            "player_uuid": TEST_PLAYER_UUID,
            "public_ip": "123.45.67.89",
            "tunnel_port": "12345"
        }
        
        resp = requests.post(
            f"{self.base_url}/api/host/update-tunnel",
            json=payload,
            headers=self.headers
        )
        
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "updated")
    
    def test_heartbeat(self):
        """POST /api/host/heartbeat"""
        self.test_register_host()
        
        payload = {
            "player_uuid": TEST_PLAYER_UUID,
            "players_online": 5,
            "tps": 19.8
        }
        
        resp = requests.post(
            f"{self.base_url}/api/host/heartbeat",
            json=payload,
            headers=self.headers
        )
        
        self.assertEqual(resp.status_code, 200)
    
    def test_get_active_host(self):
        """GET /api/state/active-host"""
        self.test_update_tunnel()
        
        resp = requests.get(
            f"{self.base_url}/api/state/active-host",
            headers=self.headers
        )
        
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["active"])
    
    def test_get_world_state(self):
        """GET /api/state/world"""
        resp = requests.get(
            f"{self.base_url}/api/state/world",
            headers=self.headers
        )
        
        self.assertEqual(resp.status_code, 200)
    
    def test_get_all_hosts(self):
        """GET /api/state/all-hosts (admin)"""
        self.test_register_host()
        
        resp = requests.get(
            f"{self.base_url}/api/state/all-hosts",
            headers=self.headers
        )
        
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("hosts", data)
    
    def test_auth_required(self):
        """Sem API key deve retornar 401"""
        resp = requests.post(
            f"{self.base_url}/api/host/register",
            json={}
        )
        
        self.assertEqual(resp.status_code, 401)
    
    def test_whitelist_operations(self):
        """Testa whitelist add/check"""
        # Add
        payload = {
            "player_uuid": TEST_PLAYER_UUID,
            "player_name": TEST_PLAYER_NAME
        }
        
        resp = requests.post(
            f"{self.base_url}/api/whitelist/add",
            json=payload,
            headers=self.headers
        )
        self.assertEqual(resp.status_code, 201)
        
        # Check
        resp = requests.get(
            f"{self.base_url}/api/whitelist/check/{TEST_PLAYER_UUID}",
            headers=self.headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["whitelisted"])
    
    def test_shutdown_host(self):
        """POST /api/host/shutdown"""
        self.test_register_host()
        
        payload = {
            "player_uuid": TEST_PLAYER_UUID,
            "save_file_hash": "abc123def456",
            "save_file_url": "s3://bucket/world.zip"
        }
        
        resp = requests.post(
            f"{self.base_url}/api/host/shutdown",
            json=payload,
            headers=self.headers
        )
        
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "shutdown_confirmed")

class TestWorldManager(unittest.TestCase):
    """Testa gerenciador de worlds."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.world_dir = Path(self.temp_dir) / "world"
        self.world_dir.mkdir()
        
        # Cria alguns arquivos dummy
        (self.world_dir / "level.dat").write_text("dummy")
        (self.world_dir / "playerdata").mkdir(exist_ok=True)
    
    def test_compress_world(self):
        """Testa compressão de world."""
        from world_manager import WorldManager, StorageConfig
        
        config = StorageConfig(
            backend="local",
            api_url="http://localhost:5000",
            api_key="test",
            local_storage_path=self.temp_dir
        )
        
        manager = WorldManager(config, world_dir=str(self.temp_dir))
        zip_path = manager.compress_world("world", self.temp_dir)
        
        self.assertIsNotNone(zip_path)
        self.assertTrue(Path(zip_path).exists())
    
    def test_calculate_hash(self):
        """Testa cálculo de hash."""
        from world_manager import WorldManager, StorageConfig
        
        config = StorageConfig(
            backend="local",
            api_url="http://localhost:5000",
            api_key="test",
            local_storage_path=self.temp_dir
        )
        
        # Cria arquivo temporário
        test_file = Path(self.temp_dir) / "test.bin"
        test_file.write_bytes(b"test content")
        
        manager = WorldManager(config, world_dir=str(self.temp_dir))
        hash1 = manager.calculate_hash(str(test_file))
        hash2 = manager.calculate_hash(str(test_file))
        
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA256

class TestHardwareAnalyzer(unittest.TestCase):
    """Testa análise de hardware."""
    
    def test_get_system_info(self):
        """Testa coleta de info de hardware."""
        from launcher_desktop import HardwareAnalyzer
        
        info = HardwareAnalyzer.get_system_info()
        
        self.assertIn("cpu_cores", info)
        self.assertIn("ram_total_gb", info)
        self.assertIn("disk_total_gb", info)
        self.assertIn("os", info)
        
        self.assertGreater(info["cpu_cores"], 0)
        self.assertGreater(info["ram_total_gb"], 0)
    
    def test_get_tier(self):
        """Testa classificação de tier."""
        from launcher_desktop import HardwareAnalyzer
        
        # Mock info
        info = {
            "cpu_cores": 8,
            "ram_total_gb": 16,
            "disk_total_gb": 200,
            "cpu_percent": 20,
            "ram_available_gb": 8,
            "disk_free_gb": 100,
            "os": "Linux"
        }
        
        tier = HardwareAnalyzer.get_tier(info)
        self.assertEqual(tier, "high")
    
    def test_is_eligible(self):
        """Testa elegibilidade."""
        from launcher_desktop import HardwareAnalyzer
        
        info = {
            "cpu_cores": 2,
            "ram_total_gb": 8,
            "ram_available_gb": 4,
            "disk_total_gb": 100,
            "disk_free_gb": 25,
            "cpu_percent": 30,
            "os": "Linux"
        }
        
        eligible = HardwareAnalyzer.is_eligible(info)
        self.assertTrue(eligible)

# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestFullFlow(unittest.TestCase):
    """Testa fluxo completo: register -> tunnel -> heartbeat -> shutdown"""
    
    def test_complete_host_lifecycle(self):
        """Simula ciclo de vida completo de um host."""
        headers = {"X-API-Key": API_KEY}
        base_url = API_URL
        player_uuid = str(uuid.uuid4())
        
        # 1. Registra host
        resp = requests.post(
            f"{base_url}/api/host/register",
            json={
                "player_uuid": player_uuid,
                "player_name": "LifecycleTest",
                "hardware_tier": "mid",
                "version": "1.20.1"
            },
            headers=headers
        )
        self.assertEqual(resp.status_code, 201)
        
        # 2. Atualiza túnel
        resp = requests.post(
            f"{base_url}/api/host/update-tunnel",
            json={
                "player_uuid": player_uuid,
                "public_ip": "203.0.113.42",
                "tunnel_port": "54321"
            },
            headers=headers
        )
        self.assertEqual(resp.status_code, 200)
        
        # 3. Envia heartbeats
        for i in range(3):
            resp = requests.post(
                f"{base_url}/api/host/heartbeat",
                json={
                    "player_uuid": player_uuid,
                    "players_online": i,
                    "tps": 20
                },
                headers=headers
            )
            self.assertEqual(resp.status_code, 200)
            time.sleep(0.5)
        
        # 4. Verifica host ativo
        resp = requests.get(
            f"{base_url}/api/state/active-host",
            headers=headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["active"])
        
        # 5. Shutdown
        resp = requests.post(
            f"{base_url}/api/host/shutdown",
            json={
                "player_uuid": player_uuid,
                "save_file_hash": "finalHash123",
                "save_file_url": "s3://bucket/world_final.zip"
            },
            headers=headers
        )
        self.assertEqual(resp.status_code, 200)

# ============================================================================
# CLI TEST RUNNER
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Define test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestNomadAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestWorldManager))
    suite.addTests(loader.loadTestsFromTestCase(TestHardwareAnalyzer))
    suite.addTests(loader.loadTestsFromTestCase(TestFullFlow))
    
    # Run
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit code
    sys.exit(0 if result.wasSuccessful() else 1)
