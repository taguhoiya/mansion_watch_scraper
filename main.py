from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.apis import api_router
from app.configs.settings import settings

app = FastAPI(title=settings.PROJECT_NAME, summary="APIs for Mansion Watch Scraper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def read_root():
    return {"message": "Welcome to Mansion Watch Scraper!"}
