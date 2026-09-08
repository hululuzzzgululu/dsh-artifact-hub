import hashlib
import uuid


def new_id(_prefix=None):
    """Return a portable business identifier independent of database row IDs."""

    return str(uuid.uuid4())


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
