from contextlib import asynccontextmanager

from fastapi import FastAPI

from dependencies.db import create_db_engine, create_db_sessionmaker
from dependencies.valkey import create_valkey_client
from utils.config import AppConfig

from api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
	config = AppConfig()
	app.state.settings = config

	app.state.db_engine = create_db_engine(config.db_url)
	app.state.db_sessionmaker = create_db_sessionmaker(app.state.db_engine)
	app.state.valkey = create_valkey_client(config.valkey_url)

	app.include_router(api_router)

	try:
		yield
	finally:
		await app.state.valkey.aclose()
		await app.state.db_engine.dispose()

