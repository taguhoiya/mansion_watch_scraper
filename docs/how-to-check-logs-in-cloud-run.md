# Cloud Run Logging Guide

## Overview
This guide explains how to effectively monitor and retrieve logs from your Cloud Run services, which is essential for debugging, monitoring, and maintaining your applications.

## Real-time Log Monitoring

### Basic Log Tailing
```bash
gcloud beta run services logs tail mansion-watch-scraper --region asia-northeast1
```
This command provides a real-time stream of all logs from your service.

### Enhanced Log Formatting
```bash
gcloud beta run services logs tail mansion-watch-scraper \
    --region asia-northeast1 \
    --format="table(timestamp,severity,textPayload,jsonPayload.message)"
```
This command displays logs in a structured table format with:
- timestamp: When the log was generated
- severity: Log level (INFO, ERROR, etc.)
- textPayload: Plain text log message
- jsonPayload.message: Structured log data

### Configuration Optimization
Set a default region to simplify subsequent commands:
```bash
gcloud config set run/region asia-northeast1
```

## Historical Log Analysis

### Querying Past Logs
```bash
gcloud logging read \
    "resource.type=cloud_run_revision AND resource.labels.service_name=mansion-watch-scraper" \
    --limit=50 \
    --format="table(timestamp,textPayload)" | cat
```

#### Query Parameters Explained
- `resource.type=cloud_run_revision`: Filters logs from Cloud Run services
- `resource.labels.service_name=mansion-watch-scraper`: Specifies the target service
- `--limit=50`: Returns the last 50 log entries
- `| cat`: Ensures proper output in CI/CD environments

## Best Practices

### Log Filtering
- Use specific severity levels for focused debugging
- Add service-specific labels for better organization
- Combine filters for precise log analysis

### Common Issues and Solutions
1. No logs appearing
   - Verify service name and region
   - Check if your service is actively running
2. Permission errors
   - Ensure you have the required IAM roles (roles/logging.viewer)

### Performance Tips
- Use appropriate limits to avoid overwhelming output
- Add specific time ranges for faster queries
- Consider exporting logs for long-term analysis
