from fastapi import APIRouter

public_router = APIRouter(prefix="/public", tags=["Plugin: Test Plugin Public"])


@public_router.get("/ping")
async def ping() -> dict:
    return {"pong": True, "plugin": "test-plugin"}
