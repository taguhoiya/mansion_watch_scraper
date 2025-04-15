# Deploying the Job Trace Server

This guide explains how to deploy the Job Trace server to Cloud Run.

## 1. Build and push the Docker image

```sh
# Build the Docker image
docker build -f mansion_watch_scraper/pubsub/Dockerfile.job_trace -t asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-job-trace:latest .

# Tag the image
docker tag asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-job-trace:latest asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-job-trace:latest

# Push the image to Artifact Registry
docker push asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-job-trace:latest
```

## 2. Deploy the service to Cloud Run

```sh
gcloud run deploy mansion-watch-job-trace \
  --image asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-job-trace:latest \
  --region asia-northeast1 \
  --platform managed \
  --memory 512Mi \
  --cpu 1 \
  --port 8081 \
  --allow-unauthenticated \
  --set-env-vars=JOB_TRACE_PORT=8081,COLLECTION_JOB_TRACES=job_traces
```

> Note: The `--allow-unauthenticated` flag makes the service publicly accessible. For production, you may want to use authentication.

## 3. Update frontend application

Update the frontend application to use the job trace API for polling job status. The API endpoints are:

- `GET /job/status?message_id={message_id}` - Get job status by message ID
- `GET /job/user?line_user_id={line_user_id}&limit={limit}&skip={skip}` - Get jobs for a specific user

The FastAPI endpoints are also available at:

- `GET /api/v1/jobs/status/{message_id}` - Get job status by message ID
- `GET /api/v1/jobs/user/{line_user_id}?limit={limit}&skip={skip}` - Get jobs for a specific user

## 4. Testing the deployment

```sh
# Test the job trace server health
curl -X GET https://mansion-watch-job-trace-abcdefghij-an.a.run.app/

# Test getting a job status by message ID
curl -X GET https://mansion-watch-job-trace-abcdefghij-an.a.run.app/job/status?message_id=123456789

# Test getting jobs for a user
curl -X GET https://mansion-watch-job-trace-abcdefghij-an.a.run.app/job/user?line_user_id=U12345678&limit=10&skip=0
```
