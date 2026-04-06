import uvicorn
from fastapi import FastAPI

from . import config
from .router import router

app = FastAPI(title="Ingestion Service", version="0.2.0-mvp")
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run("services.ingestion.main:app", host="0.0.0.0", port=config.PORT, reload=True)
