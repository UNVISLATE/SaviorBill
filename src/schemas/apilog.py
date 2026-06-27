from pydantic import BaseModel, ConfigDict

class APIMeta(BaseModel):
    method: str
    path: str
    domain: str
    status_code: int
    ip: str
    duration: float
    user_agent: str | None = None

class APILog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    tenant_id: int | None = None
    profile_id: int | None = None
    meta: APIMeta