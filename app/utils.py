# backend/app/utils.py
import hashlib

def sha256_from_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()
