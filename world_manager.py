"""
PEAR PROJECT (Nomad Server) - GERENCIADOR DE PERSISTÊNCIA
Refatorado para operações assíncronas (Non-Blocking I/O) com ThreadPoolExecutor.
Suporta S3, Google Drive, e servidor local.
"""

import os
import shutil
import zipfile
import hashlib
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG
# ============================================================================

@dataclass
class StorageConfig:
    backend: str  # "s3", "gdrive", "local"
    api_url: str
    api_key: str

    # S3
    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None

    # Google Drive
    gdrive_folder_id: Optional[str] = None
    gdrive_service_account_json: Optional[str] = None

    # Local server
    local_storage_path: Optional[str] = None
    local_server_url: Optional[str] = None

# ============================================================================
# STORAGE BACKENDS (Síncronos, isolados em Threads posteriormente)
# ============================================================================

class StorageBackend(ABC):
    @abstractmethod
    def upload(self, file_path: str, remote_name: str) -> Dict:
        pass

    @abstractmethod
    def download(self, remote_name: str, local_path: str) -> bool:
        pass

class LocalBackend(StorageBackend):
    """Backend servidor local (para testes ou VPS própria)."""

    def __init__(self, config: StorageConfig):
        self.config = config
        self.storage_path = Path(config.local_storage_path or "/tmp/pear_storage")
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def upload(self, file_path: str, remote_name: str) -> Dict:
        try:
            dest = self.storage_path / remote_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest)

            file_size = os.path.getsize(file_path)
            logger.info(f"Local upload: {remote_name} ({file_size / 1024 / 1024:.2f} MB)")

            url = f"{self.config.local_server_url}/storage/{remote_name}" if self.config.local_server_url else str(dest)

            return {
                "status": "success",
                "url": url,
                "size_mb": file_size / 1024 / 1024
            }
        except Exception as e:
            logger.error(f"Local upload error: {e}")
            return {"status": "error", "error": str(e)}

    def download(self, remote_name: str, local_path: str) -> bool:
        try:
            src = self.storage_path / remote_name
            if not src.exists():
                logger.error(f"File not found: {src}")
                return False

            shutil.copy2(src, local_path)
            logger.info(f"Local download: {remote_name} -> {local_path}")
            return True
        except Exception as e:
            logger.error(f"Local download error: {e}")
            return False

# Nota: S3Backend e GDriveBackend seguem a mesma lógica estrutural do arquivo original,
# apenas instancie as bibliotecas boto3/googleapiclient aqui da mesma forma que antes.

# ============================================================================
# WORLD MANAGER (Assíncrono e Thread-Safe)
# ============================================================================

class WorldManager:
    """Gerencia compressão, upload e download de worlds usando Threads para não bloquear a UI."""

    def __init__(self, config: StorageConfig, world_dir: str = "."):
        self.config = config
        self.world_dir = Path(world_dir)
        self.backend = self._init_backend()
        self.executor = ThreadPoolExecutor(max_workers=2)
        logging.basicConfig(level=logging.INFO)

    def _init_backend(self) -> StorageBackend:
        # Simplificado para o exemplo Local. Adicione as chamadas para S3/GDrive aqui.
        return LocalBackend(self.config)

    def _compress_world_sync(self, world_name: str, output_dir: str) -> Optional[str]:
        """Operação síncrona de compactação isolada na thread."""
        try:
            world_path = self.world_dir / world_name
            if not world_path.exists():
                logger.error(f"World not found: {world_path}")
                return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"{world_name}_{timestamp}.zip"
            zip_path = Path(output_dir) / zip_name

            logger.info(f"Compressing {world_path} to {zip_path}...")

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
                for root, _, files in os.walk(world_path):
                    for file in files:
                        if file in ["session.lock", ".pid"]: # Ignora arquivos de trava
                            continue
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(self.world_dir)
                        zipf.write(file_path, arcname)

            return str(zip_path)
        except Exception as e:
            logger.error(f"Compression error: {e}")
            return None

    def _calculate_hash_sync(self, file_path: str) -> str:
        """Operação síncrona de Hash isolada na thread."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def upload_world_async(self, world_name: str = "world") -> Dict:
        """
        Método assíncrono para upload do mundo.
        Pode ser chamado pela interface gráfica sem congelar a tela.
        """
        loop = asyncio.get_running_loop()

        try:
            # 1. Compacta o mundo (I/O pesada)
            zip_path = await loop.run_in_executor(self.executor, self._compress_world_sync, world_name, ".")
            if not zip_path:
                return {"status": "error", "error": "Compression failed"}

            # 2. Calcula o Hash (CPU pesada)
            file_hash = await loop.run_in_executor(self.executor, self._calculate_hash_sync, zip_path)

            # 3. Faz o upload (Rede pesada)
            remote_name = f"worlds/{world_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            result = await loop.run_in_executor(self.executor, self.backend.upload, zip_path, remote_name)

            if result["status"] == "success":
                result["file_hash"] = file_hash

            # Limpeza do zip temporário
            try:
                os.remove(zip_path)
            except OSError:
                pass

            return result

        except Exception as e:
            logger.error(f"Async upload error: {e}")
            return {"status": "error", "error": str(e)}

    async def download_world_async(self, save_url: str, world_name: str = "world") -> bool:
        """Método assíncrono para download do mundo."""
        loop = asyncio.get_running_loop()
        temp_zip = Path("/tmp") / f"{world_name}_temp.zip"
        remote_name = Path(save_url).name

        try:
            # 1. Faz o download
            success = await loop.run_in_executor(self.executor, self.backend.download, remote_name, str(temp_zip))
            if not success:
                return False

            # 2. Descompacta
            def _extract():
                with zipfile.ZipFile(temp_zip, "r") as zipf:
                    zipf.extractall(str(self.world_dir))

            await loop.run_in_executor(self.executor, _extract)

            try:
                os.remove(temp_zip)
            except OSError:
                pass

            return True

        except Exception as e:
            logger.error(f"Async download error: {e}")
            return False