import uvicorn
from fastapi import FastAPI

from . import config
from .router import router

app = FastAPI(title="Risk Service", version="0.1.0-stub")
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run("services.risk.main:app", host="0.0.0.0", port=config.PORT, reload=True)
