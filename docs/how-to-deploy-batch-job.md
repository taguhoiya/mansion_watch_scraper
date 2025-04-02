# Deploying as a Batch Job

For running scheduled batch jobs to check property updates, you can use Google Cloud Run Jobs with Cloud Scheduler. This guide explains how to set up automated batch processing using the `/batch` endpoint.

## Prerequisites

1. Enable required APIs (see [Prerequisites](https://cloud.google.com/run/docs/execute/jobs-on-schedule#before-you-begin)):

   ```bash
   gcloud services enable cloudscheduler.googleapis.com
   gcloud services enable run.googleapis.com
   ```

2. Verify the service account has necessary permissions (see [Authentication](https://cloud.google.com/run/docs/execute/jobs-on-schedule#authentication)):
   - The service account `cloud-run-pubsub-invoker@daring-night-451212-a8.iam.gserviceaccount.com` needs Cloud Run Invoker role
   ```bash
   gcloud projects add-iam-policy-binding daring-night-451212-a8 \
     --member="serviceAccount:cloud-run-pubsub-invoker@daring-night-451212-a8.iam.gserviceaccount.com" \
     --role="roles/run.invoker"
   ```

## Endpoint Details

The `/batch` endpoint is available at:

- Production: `https://mansion-watch-scraper-1043429343651.asia-northeast1.run.app/batch`

The endpoint is designed for batch processing of property checks:

- **Purpose**: Triggers property checks for all active properties
- **Authentication**: None required (internal endpoint)
- **Request Format**:
  ```json
  {
    "line_user_id": "optional-user-id" // Optional: Process only properties for a specific user
  }
  ```
- **Response**: Returns the number of properties processed
- **Behavior**:
  - Filters for properties with `is_active=true`
  - Sets `check_only=true` for all property checks
  - Processes all properties if no `line_user_id` is provided
  - Returns 404 if provided `line_user_id` is invalid

## Deployment Steps

1. Deploy the Cloud Run job (see [Creating jobs](https://cloud.google.com/run/docs/create-jobs)):

   For first-time deployment:

   ```bash
   gcloud run jobs create mansion-watch-scraper-batch \
     --image asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:latest \
     --region asia-northeast1 \
     --args="curl","-X","POST","https://mansion-watch-scraper-1043429343651.asia-northeast1.run.app/batch","-H","Content-Type: application/json","-d","{}"
   ```

   For updating existing job:

   ```bash
   gcloud run jobs update mansion-watch-scraper-batch \
     --image asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:latest \
     --region asia-northeast1 \
     --args="curl","-X","POST","https://mansion-watch-scraper-1043429343651.asia-northeast1.run.app/batch","-H","Content-Type: application/json","-d","{}"
   ```

2. Schedule the job running every day at 00:00 (see [Schedule execution](https://cloud.google.com/run/docs/execute/jobs-on-schedule#schedule)):

   For first-time creation:

   ```bash
   gcloud scheduler jobs create http mansion-watch-daily-job \
     --schedule="0 0 * * *" \
     --time-zone="Asia/Tokyo" \
     --location asia-northeast1 \
     --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/daring-night-451212-a8/jobs/mansion-watch-scraper-batch:run" \
     --oauth-service-account-email=cloud-run-pubsub-invoker@daring-night-451212-a8.iam.gserviceaccount.com \
     --http-method POST
   ```

   For updating existing schedule:

   ```bash
   gcloud scheduler jobs update http mansion-watch-daily-job \
     --schedule="0 0 * * *" \
     --time-zone="Asia/Tokyo" \
     --location asia-northeast1 \
     --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/daring-night-451212-a8/jobs/mansion-watch-scraper-batch:run" \
     --oauth-service-account-email=cloud-run-pubsub-invoker@daring-night-451212-a8.iam.gserviceaccount.com \
     --http-method POST
   ```

## Verification

1. Verify Cloud Run job configuration (see [View job details](https://cloud.google.com/run/docs/manage-jobs#view-job)):

   ```bash
   gcloud run jobs describe mansion-watch-scraper-batch --region asia-northeast1
   ```

2. Verify Cloud Scheduler job configuration (see [View scheduled jobs](https://cloud.google.com/scheduler/docs/view-job)):

   ```bash
   gcloud scheduler jobs describe mansion-watch-daily-job --location asia-northeast1
   ```

3. Test the job execution (see [Execute jobs](https://cloud.google.com/run/docs/execute/jobs)):
   ```bash
   gcloud run jobs execute mansion-watch-scraper-batch --region asia-northeast1
   ```

## Configuration Options

For optimal batch job performance, consider these configuration options (see [Configuring jobs](https://cloud.google.com/run/docs/configuring/jobs)):

- **Memory**: Set higher limits for large property sets ([Memory limits](https://cloud.google.com/run/docs/configuring/memory-limits))
- **CPU**: Allocate more CPU for faster processing ([CPU allocation](https://cloud.google.com/run/docs/configuring/cpu))
- **Timeout**: Adjust based on your property count ([Timeout](https://cloud.google.com/run/docs/configuring/request-timeout))
- **Concurrency**: Configure max concurrent checks ([Task parallelism](https://cloud.google.com/run/docs/configuring/parallelism))

For detailed configuration, refer to:

- [Job execution environment](https://cloud.google.com/run/docs/configuring/execution-environments)
- [Memory limits](https://cloud.google.com/run/docs/configuring/memory-limits)
- [CPU allocation](https://cloud.google.com/run/docs/configuring/cpu)
- [Timeout](https://cloud.google.com/run/docs/configuring/request-timeout)

## Monitoring and Logging

The batch job logs (see [Viewing logs](https://cloud.google.com/run/docs/logging#viewing-logs)):

- Number of properties processed
- Processing start/end times
- Any errors encountered

Monitor these logs in Cloud Logging to track job performance and troubleshoot issues.

## Health Check

You can verify the service status by sending a GET request to the root endpoint:

```bash
curl https://mansion-watch-scraper-1043429343651.asia-northeast1.run.app
# Expected response: {"status": "ok"}
```
