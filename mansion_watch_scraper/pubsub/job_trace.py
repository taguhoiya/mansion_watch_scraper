import json
import logging
import logging.config
import os
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from bson import ObjectId

from app.configs.settings import LOGGING_CONFIG
from app.models.job_status import JobStatus, JobTraceModel, JobType
from app.services.dates import get_current_time

# Configure structured logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Add module context to logger
logger = logging.LoggerAdapter(
    logger,
    {
        "component": "pubsub_job_trace",
        "operation": "job_tracking",
    },
)

# MongoDB connection
_mongo_client = None
_db = None

# Collection name for job traces
COLLECTION_JOB_TRACES = os.getenv("COLLECTION_JOB_TRACES", "job_traces")


def get_db():
    """Get MongoDB database instance."""
    global _mongo_client, _db
    if _db is None:
        try:
            # Get MongoDB connection parameters from environment
            uri = os.getenv("MONGO_URI")
            if not uri:
                raise ValueError("MONGO_URI environment variable is not set")

            # Initialize MongoDB client with connection pooling settings
            _mongo_client = pymongo.MongoClient(
                uri,
                maxPoolSize=int(os.getenv("MONGO_MAX_POOL_SIZE", "50")),
                minPoolSize=int(os.getenv("MONGO_MIN_POOL_SIZE", "0")),
                maxIdleTimeMS=int(os.getenv("MONGO_MAX_IDLE_TIME_MS", "10000")),
                connectTimeoutMS=int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "20000")),
                waitQueueTimeoutMS=int(
                    os.getenv("MONGO_WAIT_QUEUE_TIMEOUT_MS", "10000")
                ),
            )

            # Get database
            db_name = os.getenv("MONGO_DATABASE", "mansion_watch")
            _db = _mongo_client[db_name]

            # Ensure indexes
            collection = _db[COLLECTION_JOB_TRACES]
            collection.create_index("message_id", unique=True, background=True)
            collection.create_index("line_user_id", background=True)
            collection.create_index("status", background=True)
            collection.create_index(
                [("created_at", pymongo.DESCENDING)], background=True
            )
            collection.create_index(
                [("updated_at", pymongo.DESCENDING)], background=True
            )

            # Add TTL index to automatically delete old records
            # This will delete records 7 days after they were created
            collection.create_index(
                [("created_at", pymongo.ASCENDING)],
                expireAfterSeconds=7 * 24 * 60 * 60,  # 7 days in seconds
                background=True,
            )

            # Also add TTL index based on completion time for completed jobs
            # This will delete successful/failed/not_found records 3 days after completion
            collection.create_index(
                [("completed_at", pymongo.ASCENDING)],
                expireAfterSeconds=3 * 24 * 60 * 60,  # 3 days in seconds
                background=True,
                partialFilterExpression={"completed_at": {"$exists": True}},
            )

            logger.info("Successfully initialized job trace database connection")
        except Exception as e:
            logger.error(
                f"Failed to initialize MongoDB: {str(e)}",
                extra={
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                },
                exc_info=True,
            )
            raise

    return _db


def create_job_trace(
    message_id: str,
    job_type: JobType,
    url: Optional[str] = None,
    line_user_id: Optional[str] = None,
    check_only: bool = False,
) -> ObjectId:
    """Create a new job trace record.

    Args:
        message_id: Pub/Sub message ID
        job_type: Type of job
        url: Optional URL being processed
        line_user_id: Optional LINE user ID
        check_only: Whether this is a check-only operation

    Returns:
        ObjectId: ID of the created job trace record
    """
    try:
        db = get_db()
        collection = db[COLLECTION_JOB_TRACES]

        # Check if record already exists
        existing = collection.find_one({"message_id": message_id})
        if existing:
            logger.info(
                f"Job trace already exists for message ID: {message_id}",
                extra={"message_id": message_id},
            )
            return existing["_id"]

        # Create new record
        job_trace = JobTraceModel(
            message_id=message_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            url=url,
            line_user_id=line_user_id,
            check_only=check_only,
            created_at=get_current_time(),
            updated_at=get_current_time(),
        )

        # Convert to dict and insert
        job_trace_dict = job_trace.model_dump(by_alias=True)
        job_trace_dict.pop("_id", None)  # Remove _id field to let MongoDB create it

        result = collection.insert_one(job_trace_dict)

        logger.info(
            f"Created job trace for message ID: {message_id}",
            extra={
                "message_id": message_id,
                "job_trace_id": str(result.inserted_id),
            },
        )

        return result.inserted_id

    except Exception as e:
        logger.error(
            f"Failed to create job trace: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
                "message_id": message_id,
            },
            exc_info=True,
        )
        raise


def update_job_status(
    message_id: str,
    status: JobStatus,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> bool:
    """Update job status.

    Args:
        message_id: Pub/Sub message ID
        status: New status
        result: Optional result data
        error: Optional error message

    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        db = get_db()
        collection = db[COLLECTION_JOB_TRACES]

        # Prepare update data
        update_data = {
            "status": status,
            "updated_at": get_current_time(),
        }

        # Add status-specific fields
        if status == JobStatus.PROCESSING:
            update_data["started_at"] = get_current_time()
        elif status in [JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.NOT_FOUND]:
            update_data["completed_at"] = get_current_time()

        # Add result or error if provided
        if result is not None:
            update_data["result"] = result
        if error is not None:
            update_data["error"] = error

        # Update record
        result = collection.update_one(
            {"message_id": message_id},
            {"$set": update_data},
        )

        if result.matched_count == 0:
            logger.warning(
                f"No job trace found for message ID: {message_id}",
                extra={"message_id": message_id},
            )
            return False

        logger.info(
            f"Updated job trace status to {status} for message ID: {message_id}",
            extra={
                "message_id": message_id,
                "status": status,
            },
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to update job status: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
                "message_id": message_id,
            },
            exc_info=True,
        )
        return False


def get_job_status(message_id: str) -> Optional[Dict[str, Any]]:
    """Get job status for a message.

    Args:
        message_id: Pub/Sub message ID

    Returns:
        Dict or None: Job status dict, or None if not found
    """
    try:
        db = get_db()
        collection = db[COLLECTION_JOB_TRACES]

        # Find job trace
        job_trace = collection.find_one({"message_id": message_id})

        if not job_trace:
            logger.warning(
                f"No job trace found for message ID: {message_id}",
                extra={"message_id": message_id},
            )
            return None

        # Convert ObjectId to string for serialization
        job_trace["_id"] = str(job_trace["_id"])

        logger.info(
            f"Retrieved job trace for message ID: {message_id}",
            extra={
                "message_id": message_id,
                "status": job_trace.get("status"),
            },
        )
        return job_trace

    except Exception as e:
        logger.error(
            f"Failed to get job status: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
                "message_id": message_id,
            },
            exc_info=True,
        )
        return None


def get_jobs_for_user(
    line_user_id: str, limit: int = 50, skip: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """Get job traces for a specific user.

    Args:
        line_user_id: LINE user ID
        limit: Maximum number of records to return
        skip: Number of records to skip (for pagination)

    Returns:
        Tuple of (job_traces, total_count)
    """
    try:
        db = get_db()
        collection = db[COLLECTION_JOB_TRACES]

        # Count total records for this user
        total_count = collection.count_documents({"line_user_id": line_user_id})

        # Get job traces
        cursor = (
            collection.find({"line_user_id": line_user_id})
            .sort("created_at", pymongo.DESCENDING)
            .skip(skip)
            .limit(limit)
        )

        # Convert to list and stringify ObjectIds
        job_traces = []
        for job_trace in cursor:
            job_trace["_id"] = str(job_trace["_id"])
            job_traces.append(job_trace)

        logger.info(
            f"Retrieved {len(job_traces)} job traces for user ID: {line_user_id}",
            extra={
                "line_user_id": line_user_id,
                "total_count": total_count,
                "returned_count": len(job_traces),
            },
        )
        return job_traces, total_count

    except Exception as e:
        logger.error(
            f"Failed to get job traces for user: {str(e)}",
            extra={
                "error": str(e),
                "error_type": e.__class__.__name__,
                "line_user_id": line_user_id,
            },
            exc_info=True,
        )
        return [], 0


class JobTraceHandler(BaseHTTPRequestHandler):
    """HTTP request handler for job trace API."""

    def _add_cors_headers(self):
        """Add CORS headers to the response."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "3600")

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self._add_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests for job status retrieval."""
        try:
            # Parse path
            path_parts = self.path.split("?")
            base_path = path_parts[0]

            # Route to appropriate handler
            if base_path == "/job/status" and len(path_parts) > 1:
                self._handle_job_status(path_parts[1])
            elif base_path == "/job/user" and len(path_parts) > 1:
                self._handle_user_jobs(path_parts[1])
            else:
                self._send_error(404, "Endpoint not found")

        except Exception as e:
            logger.error(
                f"Error processing GET request: {str(e)}",
                extra={
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                },
                exc_info=True,
            )
            self._send_error(500, f"Internal server error: {str(e)}")

    def _parse_query_params(self, query_string):
        """Parse query parameters from query string."""
        query_params = {}
        for param in query_string.split("&"):
            if "=" in param:
                key, value = param.split("=", 1)
                query_params[key] = value
        return query_params

    def _handle_job_status(self, query_string):
        """Handle job status endpoint."""
        query_params = self._parse_query_params(query_string)

        message_id = query_params.get("message_id")
        if not message_id:
            self._send_error(400, "Missing message_id parameter")
            return

        job_status = get_job_status(message_id)
        if not job_status:
            self._send_error(404, f"Job trace not found for message ID: {message_id}")
            return

        self._send_response(200, job_status)

    def _handle_user_jobs(self, query_string):
        """Handle user jobs endpoint."""
        query_params = self._parse_query_params(query_string)

        line_user_id = query_params.get("line_user_id")
        if not line_user_id:
            self._send_error(400, "Missing line_user_id parameter")
            return

        limit = int(query_params.get("limit", "50"))
        skip = int(query_params.get("skip", "0"))

        jobs, total_count = get_jobs_for_user(line_user_id, limit, skip)
        response = {
            "jobs": jobs,
            "total_count": total_count,
            "limit": limit,
            "skip": skip,
        }

        self._send_response(200, response)

    def _send_response(self, code: int, data: Any):
        """Send a JSON response."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_error(self, code: int, message: str):
        """Send an error response."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._add_cors_headers()
        self.end_headers()
        error_data = {"error": message}
        self.wfile.write(json.dumps(error_data).encode("utf-8"))
