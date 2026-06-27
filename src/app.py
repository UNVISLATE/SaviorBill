from fastapi import FastAPI

from lifespan import lifespan
from utils.config import AppConfig

settings = AppConfig()

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)