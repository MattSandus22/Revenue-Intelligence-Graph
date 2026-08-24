"""Connector credential storage — encrypted at rest, never returned by APIs,
never logged (docs/12 §12.2).

MVP crypto: Fernet (AES-128-CBC + HMAC) with a key from RIG_CREDENTIAL_KEY.
Production swaps `_fernet()` for KMS envelope encryption; the stored
ciphertext is opaque either way. The dev default key is refused outside dev
mode by rig.boot's production config check.
"""

import base64
import hashlib
import json
import os
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.orm import Session

DEV_KEY_SEED = "rig-dev-credential-key"


def _fernet() -> Fernet:
    raw = os.environ.get("RIG_CREDENTIAL_KEY")
    if raw:
        return Fernet(raw.encode())
    # deterministic dev key — flagged fatal in production by rig.boot
    derived = base64.urlsafe_b64encode(hashlib.sha256(DEV_KEY_SEED.encode()).digest())
    return Fernet(derived)


def store_credentials(session: Session, tenant_id: UUID | str,
                      data_source_id: UUID | str, secrets: dict) -> None:
    ciphertext = _fernet().encrypt(json.dumps(secrets).encode()).decode()
    session.execute(text(
        "INSERT INTO integration_credential (tenant_id, data_source_id, ciphertext)"
        " VALUES (:tid, :sid, :ct)"
        " ON CONFLICT (data_source_id)"
        " DO UPDATE SET ciphertext = EXCLUDED.ciphertext, rotated_at = now()"
    ), {"tid": str(tenant_id), "sid": str(data_source_id), "ct": ciphertext})


class CredentialDecryptError(Exception):
    """Stored ciphertext cannot be decrypted with the current key (key was
    rotated or set after storage). Recoverable: re-enter the credentials."""


def load_credentials(session: Session, data_source_id: UUID | str) -> dict | None:
    from cryptography.fernet import InvalidToken

    ciphertext = session.execute(text(
        "SELECT ciphertext FROM integration_credential WHERE data_source_id = :sid"
    ), {"sid": str(data_source_id)}).scalar_one_or_none()
    if ciphertext is None:
        return None
    try:
        return json.loads(_fernet().decrypt(ciphertext.encode()))
    except InvalidToken as exc:
        raise CredentialDecryptError(
            "stored credentials cannot be decrypted with the current "
            "RIG_CREDENTIAL_KEY — re-enter the connector credentials") from exc


def delete_credentials(session: Session, data_source_id: UUID | str) -> bool:
    deleted = session.execute(text(
        "DELETE FROM integration_credential WHERE data_source_id = :sid"
    ), {"sid": str(data_source_id)}).rowcount
    return bool(deleted)
