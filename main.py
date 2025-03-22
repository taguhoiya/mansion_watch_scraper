"""FastAPI application module."""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.apis import api_router
from app.configs.settings import LOGGING_CONFIG
from app.db.indexes import ensure_indexes
from app.db.session import get_client_options

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application.

    Args:
        app: The FastAPI application instance.

    Yields:
        None
    """
    # Startup
    try:
        app.mongodb_client = AsyncIOMotorClient(
            os.getenv("MONGO_URI"), **get_client_options()
        )
        app.mongodb = app.mongodb_client[os.getenv("MONGO_DATABASE", "mansion_watch")]
        await app.mongodb.command("ping")
        logger.info("Connected to MongoDB")
        await ensure_indexes(app.mongodb)
        yield
    except Exception as e:
        logger.error("Failed to initialize MongoDB: %s", e)
        raise
    finally:
        # Shutdown
        logger.info("Closing MongoDB connection")
        app.mongodb_client.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        The configured FastAPI application.
    """
    # Create FastAPI application
    app = FastAPI(
        title="Mansion Watch API",
        description="API for monitoring mansion listings",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_origin_regex=None,
        expose_headers=["*"],
        max_age=600,
    )

    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        """Middleware for logging request information."""

        async def dispatch(
            self, request: Request, call_next: RequestResponseEndpoint
        ) -> JSONResponse:
            """Process the request and log information.

            Args:
                request: The incoming request.
                call_next: The next middleware or endpoint.

            Returns:
                The response from the next middleware or endpoint.
            """
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            logger.info(
                "Method: %s Path: %s Status: %d Time: %.3fs",
                request.method,
                request.url.path,
                response.status_code,
                process_time,
            )
            response.headers["X-Process-Time"] = str(process_time)
            return response

    app.add_middleware(RequestLoggingMiddleware)

    # Add API router
    app.include_router(api_router)

    @app.get("/")
    async def root() -> Dict[str, str]:
        """Root endpoint.

        Returns:
            A welcome message.
        """
        return {"message": "Welcome to Mansion Watch API"}

    @app.get("/health")
    async def health_check() -> Dict[str, Any]:  # noqa: F811
        """Health check endpoint.

        Returns:
            The health status of the application.
        """
        if not hasattr(app, "mongodb") or app.mongodb is None:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": "Database not initialized",
                },
            )
        try:
            await app.mongodb.command("ping")
            return {
                "status": "healthy",
                "database": "connected",
            }
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": str(e),
                },
            )

    return app


def main():
    """Main function."""
    # Configure logging
    logging.config.dictConfig(LOGGING_CONFIG)

    # Start the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=["/app"],
    )


# Create FastAPI application instance
app = create_app()
