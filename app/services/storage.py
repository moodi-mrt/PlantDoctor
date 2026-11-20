"""Private object storage for user images and Grad-CAM overlays.

Keys are random (not guessable, not derived from user input). Files are never served from a
public path: the API streams them to their owner after an authorisation check.
"""
import secrets
from pathlib import Path

from ..config import S3_BUCKET, S3_ENDPOINT, STORAGE, UPLOAD_DIR


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str):
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self, bucket: str, endpoint: str | None):
        import boto3  # optional dependency, only needed when PD_STORAGE=s3
        self.bucket, self.s3 = bucket, boto3.client("s3", endpoint_url=endpoint)

    def put(self, key: str, data: bytes):
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str):
        self.s3.delete_object(Bucket=self.bucket, Key=key)


def new_key(prefix: str, ext: str) -> str:
    return f"{prefix}/{secrets.token_hex(2)}/{secrets.token_urlsafe(18)}.{ext}"


storage = S3Storage(S3_BUCKET, S3_ENDPOINT) if STORAGE == "s3" else LocalStorage(UPLOAD_DIR)
