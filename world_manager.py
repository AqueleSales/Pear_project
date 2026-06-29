"""
NOMAD SERVER - GERENCIADOR DE PERSISTÊNCIA
Compacta/descompacta worlds, faz upload/download de mapa.
Suporta S3, Google Drive, servidor local.
"""

import os
import shutil
import zipfile
import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass
from abc import ABC, abstractmethod
import requests
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG
# ============================================================================

@dataclass
class StorageConfig:
    backend: str  # "s3", "gdrive", "local"
    api_url: str  # URL da API Nomad
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
# STORAGE BACKENDS
# ============================================================================

class StorageBackend(ABC):
    """Interface abstrata para backends de storage."""
    
    @abstractmethod
    def upload(self, file_path: str, remote_name: str) -> Dict:
        pass
    
    @abstractmethod
    def download(self, remote_name: str, local_path: str) -> bool:
        pass
    
    @abstractmethod
    def exists(self, remote_name: str) -> bool:
        pass
    
    @abstractmethod
    def delete(self, remote_name: str) -> bool:
        pass

class S3Backend(StorageBackend):
    """Backend AWS S3."""
    
    def __init__(self, config: StorageConfig):
        self.config = config
        try:
            import boto3
            self.s3 = boto3.client(
                "s3",
                region_name=config.s3_region,
                aws_access_key_id=config.s3_access_key,
                aws_secret_access_key=config.s3_secret_key
            )
        except ImportError:
            raise ImportError("boto3 required for S3 backend: pip install boto3")
    
    def upload(self, file_path: str, remote_name: str) -> Dict:
        try:
            file_size = os.path.getsize(file_path)
            self.s3.upload_file(
                file_path,
                self.config.s3_bucket,
                remote_name,
                ExtraArgs={"ServerSideEncryption": "AES256"}
            )
            logger.info(f"S3 upload: {remote_name} ({file_size / 1024 / 1024:.2f} MB)")
            return {
                "status": "success",
                "url": f"s3://{self.config.s3_bucket}/{remote_name}",
                "size_mb": file_size / 1024 / 1024
            }
        except Exception as e:
            logger.error(f"S3 upload error: {e}")
            return {"status": "error", "error": str(e)}
    
    def download(self, remote_name: str, local_path: str) -> bool:
        try:
            self.s3.download_file(self.config.s3_bucket, remote_name, local_path)
            logger.info(f"S3 download: {remote_name} -> {local_path}")
            return True
        except Exception as e:
            logger.error(f"S3 download error: {e}")
            return False
    
    def exists(self, remote_name: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.config.s3_bucket, Key=remote_name)
            return True
        except:
            return False
    
    def delete(self, remote_name: str) -> bool:
        try:
            self.s3.delete_object(Bucket=self.config.s3_bucket, Key=remote_name)
            return True
        except:
            return False

class GDriveBackend(StorageBackend):
    """Backend Google Drive."""
    
    def __init__(self, config: StorageConfig):
        self.config = config
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
            
            self.service_account = service_account
            self.build = build
            self.MediaFileUpload = MediaFileUpload
            self.MediaIoBaseDownload = MediaIoBaseDownload
            self.io = __import__('io')
            
            creds = service_account.Credentials.from_service_account_file(
                config.gdrive_service_account_json,
                scopes=["https://www.googleapis.com/auth/drive"]
            )
            self.drive = build("drive", "v3", credentials=creds)
        except ImportError:
            raise ImportError("google-auth, google-auth-oauthlib, google-auth-httplib2, google-api-python-client required")
    
    def upload(self, file_path: str, remote_name: str) -> Dict:
        try:
            file_size = os.path.getsize(file_path)
            file_metadata = {
                "name": remote_name,
                "parents": [self.config.gdrive_folder_id]
            }
            media = self.MediaFileUpload(file_path, resumable=True)
            file = self.drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink"
            ).execute()
            
            logger.info(f"Google Drive upload: {remote_name} ({file_size / 1024 / 1024:.2f} MB)")
            return {
                "status": "success",
                "url": file.get("webViewLink"),
                "file_id": file.get("id"),
                "size_mb": file_size / 1024 / 1024
            }
        except Exception as e:
            logger.error(f"Google Drive upload error: {e}")
            return {"status": "error", "error": str(e)}
    
    def download(self, remote_name: str, local_path: str) -> bool:
        try:
            results = self.drive.files().list(
                q=f"name='{remote_name}' and trashed=false",
                spaces="drive",
                fields="files(id)"
            ).execute()
            files = results.get("files", [])
            
            if not files:
                logger.error(f"File not found on Google Drive: {remote_name}")
                return False
            
            file_id = files[0]["id"]
            request = self.drive.files().get_media(fileId=file_id)
            
            with self.io.FileIO(local_path, "wb") as fh:
                downloader = self.MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            logger.info(f"Google Drive download: {remote_name} -> {local_path}")
            return True
        except Exception as e:
            logger.error(f"Google Drive download error: {e}")
            return False
    
    def exists(self, remote_name: str) -> bool:
        try:
            results = self.drive.files().list(
                q=f"name='{remote_name}' and trashed=false",
                spaces="drive",
                fields="files(id)"
            ).execute()
            return len(results.get("files", [])) > 0
        except:
            return False
    
    def delete(self, remote_name: str) -> bool:
        try:
            results = self.drive.files().list(
                q=f"name='{remote_name}' and trashed=false",
                spaces="drive",
                fields="files(id)"
            ).execute()
            files = results.get("files", [])
            
            for file in files:
                self.drive.files().delete(fileId=file["id"]).execute()
            
            return True
        except:
            return False

class LocalBackend(StorageBackend):
    """Backend servidor local (para testes ou VPS própria)."""
    
    def __init__(self, config: StorageConfig):
        self.config = config
        self.storage_path = Path(config.local_storage_path or "/tmp/nomad_storage")
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def upload(self, file_path: str, remote_name: str) -> Dict:
        try:
            dest = self.storage_path / remote_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest)
            
            file_size = os.path.getsize(file_path)
            logger.info(f"Local upload: {remote_name} ({file_size / 1024 / 1024:.2f} MB)")
            
            # Se há servidor local, gera URL
            if self.config.local_server_url:
                url = f"{self.config.local_server_url}/storage/{remote_name}"
            else:
                url = str(dest)
            
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
    
    def exists(self, remote_name: str) -> bool:
        return (self.storage_path / remote_name).exists()
    
    def delete(self, remote_name: str) -> bool:
        try:
            path = self.storage_path / remote_name
            if path.exists():
                if path.is_file():
                    path.unlink()
                else:
                    shutil.rmtree(path)
            return True
        except:
            return False

# ============================================================================
# WORLD MANAGER
# ============================================================================

class WorldManager:
    """Gerencia compressão, upload e download de worlds."""
    
    def __init__(self, config: StorageConfig, world_dir: str = "."):
        self.config = config
        self.world_dir = Path(world_dir)
        self.backend = self._init_backend()
        logger.basicConfig(level=logging.INFO)
    
    def _init_backend(self) -> StorageBackend:
        """Inicializa backend apropriado."""
        if self.config.backend == "s3":
            return S3Backend(self.config)
        elif self.config.backend == "gdrive":
            return GDriveBackend(self.config)
        else:
            return LocalBackend(self.config)
    
    def compress_world(self, world_name: str = "world", output_dir: str = ".") -> Optional[str]:
        """
        Compacta pasta 'world' em ZIP com compressão máxima.
        Retorna caminho do arquivo compactado.
        """
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
                for root, dirs, files in os.walk(world_path):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(self.world_dir)
                        zipf.write(file_path, arcname)
                        
                        # Skip PID, session.lock e outros temporários
                        if file in ["session.lock", ".pid"]:
                            continue
            
            size_mb = os.path.getsize(zip_path) / 1024 / 1024
            logger.info(f"Compression complete: {size_mb:.2f} MB")
            
            return str(zip_path)
        
        except Exception as e:
            logger.error(f"Compression error: {e}")
            return None
    
    def extract_world(self, zip_path: str, extract_to: str = ".") -> bool:
        """
        Descompacta ZIP de world.
        """
        try:
            logger.info(f"Extracting {zip_path} to {extract_to}...")
            
            with zipfile.ZipFile(zip_path, "r") as zipf:
                zipf.extractall(extract_to)
            
            logger.info("Extraction complete")
            return True
        
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return False
    
    def calculate_hash(self, file_path: str) -> str:
        """
        Calcula SHA256 de um arquivo (para verificar integridade).
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def upload_world(self, world_name: str = "world") -> Dict:
        """
        Compacta e faz upload de world.
        Notifica API do Nomad ao terminar.
        """
        try:
            # Compacta
            zip_path = self.compress_world(world_name)
            if not zip_path:
                return {"status": "error", "error": "Compression failed"}
            
            # Calcula hash
            file_hash = self.calculate_hash(zip_path)
            
            # Faz upload
            remote_name = f"worlds/{world_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            result = self.backend.upload(zip_path, remote_name)
            
            if result["status"] != "success":
                return result
            
            # Notifica API
            save_url = result.get("url")
            self._notify_api_save(file_hash, save_url)
            
            # Limpa local
            try:
                os.remove(zip_path)
            except:
                pass
            
            return {
                "status": "success",
                "file_hash": file_hash,
                "save_url": save_url,
                "size_mb": result["size_mb"]
            }
        
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return {"status": "error", "error": str(e)}
    
    def download_world(self, save_url: str, world_name: str = "world") -> bool:
        """
        Faz download de world do storage.
        """
        try:
            temp_zip = Path("/tmp") / f"{world_name}_temp.zip"
            
            # Extrai nome do arquivo do save_url
            if save_url.startswith("s3://"):
                remote_name = save_url.split("s3://")[1].split("/", 1)[1]
            else:
                remote_name = Path(save_url).name
            
            logger.info(f"Downloading {remote_name}...")
            
            if not self.backend.download(remote_name, str(temp_zip)):
                return False
            
            # Extrai
            if not self.extract_world(str(temp_zip), str(self.world_dir)):
                return False
            
            # Limpa temp
            try:
                os.remove(temp_zip)
            except:
                pass
            
            return True
        
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False
    
    def _notify_api_save(self, file_hash: str, save_url: str):
        """
        Notifica API que o mundo foi salvo.
        """
        try:
            # (Chamado por launcher ao desligar)
            pass
        except Exception as e:
            logger.error(f"API notification error: {e}")

# ============================================================================
# CLEANUP & UTILITIES
# ============================================================================

class WorldCleanup:
    """Limpeza automática de backups antigos."""
    
    def __init__(self, backend: StorageBackend, max_backups: int = 5):
        self.backend = backend
        self.max_backups = max_backups
    
    def cleanup_old_backups(self, world_name: str):
        """
        Mantém apenas N backups mais recentes.
        """
        # TODO: implementar cleanup com base em timestamps
        pass

if __name__ == "__main__":
    # Exemplo de uso
    config = StorageConfig(
        backend="local",
        api_url="http://localhost:5000",
        api_key="your-key",
        local_storage_path="/tmp/nomad_storage"
    )
    
    manager = WorldManager(config, world_dir=".")
    
    # Upload
    result = manager.upload_world("world")
    print(result)
    
    # Download
    # manager.download_world("s3://bucket/worlds/world_20240101_120000.zip")
