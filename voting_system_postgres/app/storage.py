from __future__ import annotations

import secrets
from pathlib import Path
from typing import Tuple

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .config import Config
from .security import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_PROOF_EXTENSIONS, allowed_file, encrypt_bytes, decrypt_bytes

MAX_UPLOAD_BYTES = 6 * 1024 * 1024


def _read_limited(file: FileStorage) -> bytes:
    data = file.read()
    file.seek(0)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file is too large. Maximum allowed size is 6 MB.")
    return data


def save_image(file: FileStorage | None, prefix: str) -> str | None:
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
        raise ValueError("Only PNG, JPG, JPEG, and WEBP images are allowed.")
    data = _read_limited(file)
    ext = file.filename.rsplit(".", 1)[-1].lower()
    filename = f"{prefix}_{secrets.token_hex(12)}.{ext}"
    path = Config.UPLOAD_DIR / filename
    path.write_bytes(data)
    return filename


def save_proof(file: FileStorage | None, prefix: str) -> Tuple[str | None, str | None]:
    if not file or not file.filename:
        return None, None
    if not allowed_file(file.filename, ALLOWED_PROOF_EXTENSIONS):
        raise ValueError("Proof must be PNG, JPG, JPEG, WEBP, or PDF.")
    data = _read_limited(file)
    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[-1].lower()
    encrypted_name = f"{prefix}_{secrets.token_hex(12)}.{ext}.enc"
    (Config.UPLOAD_DIR / encrypted_name).write_bytes(encrypt_bytes(data))
    return encrypted_name, original_name


def read_encrypted_file(filename: str) -> bytes:
    safe = Path(filename).name
    path = Config.UPLOAD_DIR / safe
    return decrypt_bytes(path.read_bytes())
