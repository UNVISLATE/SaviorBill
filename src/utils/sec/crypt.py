import secrets


def generate_base_token() -> str:
    return secrets.token_urlsafe(32)
