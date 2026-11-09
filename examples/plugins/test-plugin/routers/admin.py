from fastapi import APIRouter

admin_router = APIRouter(prefix="/admin", tags=["Plugin: Test Plugin Admin"])


@admin_router.get("/status")
async def get_test_status() -> dict:
    return {"status": "ok", "plugin": "test-plugin", "author": "UNVI.XYZ"}
