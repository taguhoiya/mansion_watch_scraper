"""FastAPI application module."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.apis import api_router
from app.configs.settings import LOGGING_CONFIG
from app.db.indexes import ensure_indexes
from app.db.session import get_client, init_db

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
        # Initialize MongoDB connection with retry logic
        await init_db()
        app.mongodb_client = get_client()
        app.mongodb = app.mongodb_client[os.getenv("MONGO_DATABASE", "mansion_watch")]
        logger.info("Connected to MongoDB")
        await ensure_indexes(app.mongodb)
        yield
    except Exception as e:
        logger.error("Failed to initialize MongoDB: %s", e)
        raise
    finally:
        # Shutdown - only close if we successfully created the client
        if hasattr(app, "mongodb_client"):
            logger.info("Closing MongoDB connection")
            app.mongodb_client.close()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging request information."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse:
        """Process the request and log information."""
        start_time = time.time()
        request_id = str(uuid.uuid4())  # Generate unique request ID
        try:
            # Extract trace context
            trace_header = request.headers.get("X-Cloud-Trace-Context")
            if trace_header:
                trace = trace_header.split("/")
                trace_id = trace[0]
                # Add trace context to logging
                logger.info(
                    "Processing request",
                    extra={
                        "trace": trace_id,
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    },
                )

            response = await call_next(request)
            process_time = time.time() - start_time

            # Log response with trace context if available
            log_extra = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time,
            }
            if trace_header:
                log_extra["trace"] = trace_id

            logger.info(
                f"Method: {request.method} Path: {request.url.path} Status: {response.status_code} Time: {process_time:.3f}s",
                extra=log_extra,
            )

            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Request-ID"] = (
                request_id  # Add request ID to response headers
            )
            return response

        except Exception as e:
            # Log error with trace context if available
            log_extra = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
            }
            if trace_header:
                log_extra["trace"] = trace_id

            logger.error(
                f"Error processing request: Method: {request.method} Path: {request.url.path} Error: {str(e)}",
                extra=log_extra,
                exc_info=True,
            )
            raise


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://mansionwatchweb.vercel.app", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=600,
    )


def setup_routes(app: FastAPI) -> None:
    """Configure application routes.

    Args:
        app: FastAPI application instance
    """

    @app.get("/")
    async def root() -> Dict[str, str]:
        """Root endpoint."""
        return {"message": "Welcome to Mansion Watch API"}

    @app.get("/health")
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint."""
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
            await app.mongodb.command("ping", maxTimeMS=5000)
            return {"status": "healthy", "database": "connected"}
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


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        The configured FastAPI application.
    """
    app = FastAPI(
        title="Mansion Watch API",
        description="API for monitoring mansion listings",
        version="1.0.0",
        lifespan=lifespan,
    )

    setup_cors(app)
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(api_router)
    setup_routes(app)

    return app


def main():
    """Main function."""
    # Configure logging
    logging.config.dictConfig(LOGGING_CONFIG)

    # Configure Uvicorn logging to use our structured format
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = []  # Remove default handlers
    uvicorn_logger.addHandler(
        logging.getLogger().handlers[0]
    )  # Use our structured handler

    # Start the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=["/app"],
        log_config=None,  # Disable Uvicorn's logging config
    )


# Create FastAPI application instance
app = create_app()
