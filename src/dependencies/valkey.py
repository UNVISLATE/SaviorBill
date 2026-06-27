from typing import Any

from fastapi import Request
import valkey.asyncio as valkey

def create_valkey_client(url: str, **kwargs: Any) -> valkey.Valkey:
	"""Создать асинхронного клиента Valkey."""
	return valkey.from_url(url, decode_responses=True, **kwargs)


async def get_valkey_client(request: Request) -> valkey.Valkey:
	"""Получить клиента Valkey из `app.state`."""
	return request.app.state.valkey