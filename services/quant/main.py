import uvicorn
from fastapi import FastAPI

from . import config
from .router import router

app = FastAPI(title="Quant Service", version="0.3.0-fundamental")
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run("services.quant.main:app", host="0.0.0.0", port=config.PORT, reload=True)
