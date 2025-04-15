# Job Trace System for Mansion Watch Scraper

This module implements a job tracing system for the Mansion Watch Scraper to track the status of Pub/Sub messages and their processing jobs.

## Components

1. **Job Status Model** (`app/models/job_status.py`):

   - Provides data models for job status tracking
   - Defines enums for job statuses (QUEUED, PROCESSING, SUCCESS, FAILED, NOT_FOUND)
   - Defines job types (PROPERTY_SCRAPE, BATCH_CHECK)

2. **Job Trace Module** (`mansion_watch_scraper/pubsub/job_trace.py`):

   - Core implementation for job trace CRUD operations
   - MongoDB integration for storing job traces
   - HTTP handler for standalone server mode

3. **Job Trace Server** (`mansion_watch_scraper/pubsub/job_trace_server.py`):

   - Standalone HTTP server for job trace API
   - Can be deployed separately as a microservice

4. **FastAPI Integration** (`app/apis/job_trace.py`):

   - FastAPI endpoints for accessing job traces
   - Provides REST API for frontend applications

5. **Pub/Sub Service Integration** (`mansion_watch_scraper/pubsub/service.py`):
   - Updated to create and update job traces during message processing
   - Tracks job status through the entire processing lifecycle

## Deployment

Two deployment options are available:

1. **As part of the main API**:

   - FastAPI endpoints at `/api/v1/jobs/status/{message_id}` and `/api/v1/jobs/user/{line_user_id}`
   - Integrated with the existing API server

2. **As a standalone service**:
   - HTTP endpoints at `/job/status?message_id={message_id}` and `/job/user?line_user_id={line_user_id}`
   - Deployable separately to Cloud Run using `Dockerfile.job_trace`
   - See `docs/how-to-deploy-job-trace-server.md` for deployment instructions

## Database Schema

The `job_traces` collection stores job trace records with the following structure:

```json
{
  "_id": ObjectId("..."),
  "message_id": "string",
  "job_type": "property_scrape|batch_check",
  "status": "queued|processing|success|failed|not_found",
  "url": "string (optional)",
  "line_user_id": "string (optional)",
  "check_only": boolean,
  "created_at": ISODate("..."),
  "updated_at": ISODate("..."),
  "started_at": ISODate("..."),
  "completed_at": ISODate("..."),
  "error": "string (optional)",
  "result": {
    // Result data object (optional)
  }
}
```

### Database Indexes

The `job_traces` collection includes the following indexes:

1. `message_id` (unique) - For fast lookups by message ID
2. `line_user_id` - For retrieving user-specific job traces
3. `status` - For filtering by job status
4. `created_at` (descending) - For sorting by creation time
5. `updated_at` (descending) - For sorting by last update time

### TTL Indexes for Automatic Cleanup

Two TTL (Time-To-Live) indexes are configured for automatic cleanup of old records:

1. **Based on creation time**:

   - Documents are automatically deleted 7 days after they are created
   - Ensures that all job traces are eventually removed
   - Index: `created_at` with `expireAfterSeconds: 604800` (7 days)

2. **Based on completion time**:
   - Completed jobs (success, failed, not_found) are deleted 3 days after completion
   - Only applies to documents with a `completed_at` field
   - Index: `completed_at` with `expireAfterSeconds: 259200` (3 days)

These TTL indexes help keep the database size manageable and prevent it from growing indefinitely with historical job traces.

## API Usage

### 1. Get job status by message ID

```
GET /api/v1/jobs/status/{message_id}
```

Example response:

```json
{
  "id": "64a5b2e1a2b3c4d5e6f7a8b9",
  "message_id": "1234567890",
  "status": "success",
  "url": "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_98142765/",
  "line_user_id": "U1234567890abcdef",
  "check_only": false,
  "created_at": "2023-06-01T12:34:56.789Z",
  "updated_at": "2023-06-01T12:35:42.123Z",
  "started_at": "2023-06-01T12:35:01.456Z",
  "completed_at": "2023-06-01T12:35:42.123Z",
  "error": null,
  "result": {
    "status": "success",
    "property_info": {
      "properties": {
        "name": "Example Property"
      }
    }
  }
}
```

### 2. Get jobs for a specific user

```
GET /api/v1/jobs/user/{line_user_id}?limit=10&skip=0
```

Example response:

```json
{
  "jobs": [
    {
      "id": "64a5b2e1a2b3c4d5e6f7a8b9",
      "message_id": "1234567890",
      "status": "success",
      "url": "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_98142765/",
      "line_user_id": "U1234567890abcdef",
      "check_only": false,
      "created_at": "2023-06-01T12:34:56.789Z",
      "updated_at": "2023-06-01T12:35:42.123Z",
      "started_at": "2023-06-01T12:35:01.456Z",
      "completed_at": "2023-06-01T12:35:42.123Z",
      "error": null,
      "result": {
        "status": "success"
      }
    }
  ],
  "total_count": 42,
  "limit": 10,
  "skip": 0
}
```

## Frontend Integration

Frontend applications should update their polling logic:

1. After queuing a scraping job, receive the `message_id` in the response
2. Use the job trace API to poll for status updates:

   ```js
   async function checkJobStatus(messageId) {
     const response = await fetch(`/api/v1/jobs/status/${messageId}`);
     const jobStatus = await response.json();

     // Check job status and update UI accordingly
     if (jobStatus.status === "success") {
       showSuccess(jobStatus.result);
     } else if (
       jobStatus.status === "failed" ||
       jobStatus.status === "not_found"
     ) {
       showError(jobStatus.error);
     } else {
       // Still processing, continue polling
       setTimeout(() => checkJobStatus(messageId), 2000);
     }
   }
   ```
