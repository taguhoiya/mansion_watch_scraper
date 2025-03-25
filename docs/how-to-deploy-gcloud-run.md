# Deploying to Google Cloud Run

## Prerequisites

### Required Tools
- Google Cloud SDK (gcloud CLI)
- Docker
- Access to Google Cloud project with required permissions

### Initial Setup
1. Install Google Cloud SDK
2. Install Docker
3. Configure Docker authentication with Google Cloud:
   ```bash
   gcloud auth configure-docker
   ```

## Local Development

### Building the Container
Build the Docker image locally to test:
```bash
docker build -t mansion-watch-scraper -f mansion_watch_scraper/pubsub/Dockerfile .
```

### Testing Locally
Run the container locally to verify functionality:
```bash
docker run -p 8081:8080 --env-file .env.prod mansion-watch-scraper
```

The service will be available at `http://localhost:8081`

## Deployment

### 1. Tag the Container
Tag the container for Google Container Registry:
```bash
docker tag mansion-watch-scraper asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:latest
```

### 2. Push to Container Registry
Push the container to Google Container Registry:
```bash
docker push asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:latest
```

### 3. Deploy to Cloud Run
Deploy the service to Cloud Run:
```bash
gcloud run deploy mansion-watch-scraper \
  --image asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:latest \
  --region asia-northeast1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080
```

#### Deployment Parameters Explained
- `--region asia-northeast1`: Deploys to Tokyo region
- `--platform managed`: Uses fully managed Cloud Run service
- `--allow-unauthenticated`: Allows public access
- `--port 8080`: Container listens on port 8080

## Environment Variables

### Local Development
- Create `.env.prod` file for local testing
- Never commit sensitive environment variables to version control

### Cloud Run
1. Set environment variables in Cloud Run console
2. For sensitive data, use Secret Manager:
   ```bash
   # Create secret
   gcloud secrets create MY_SECRET --data-file=./secret.txt
   
   # Grant access to Cloud Run
   gcloud secrets add-iam-policy-binding MY_SECRET \
     --member=serviceAccount:service-account@project.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor
   ```

## Monitoring and Verification

### Health Check
1. After deployment, Cloud Run provides a URL
2. Test the endpoint:
   ```bash
   curl https://mansion-watch-scraper-xxxxx-an.a.run.app/health
   ```

### Monitoring
1. View logs in Cloud Console
2. Set up Cloud Monitoring alerts
3. Configure uptime checks

## Troubleshooting

### Common Issues
1. Container fails to start
   - Check logs in Cloud Console
   - Verify environment variables
   - Check container health check

2. Permission issues
   - Verify IAM roles
   - Check service account permissions

3. Resource constraints
   - Review memory usage
   - Check CPU utilization

## Cost Management

### Optimization Tips
1. Use minimum instances wisely
2. Configure concurrency appropriately
3. Set memory limits correctly
4. Use cold starts strategically

### Monitoring Costs
1. Set up budget alerts
2. Monitor usage regularly
3. Review and optimize resource allocation

## Security Best Practices

1. Use latest base images
2. Implement least privilege access
3. Regularly update dependencies
4. Use Secret Manager for sensitive data
5. Enable Container-Optimized OS

## Version Management

Instead of using `latest` tag, use semantic versioning:
```bash
# Tag with version
docker tag mansion-watch-scraper asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:v1.0.0

# Push versioned image
docker push asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:v1.0.0

# Deploy specific version
gcloud run deploy mansion-watch-scraper \
  --image asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-scraper:v1.0.0 \
  --region asia-northeast1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080
```

## CI/CD Integration

Consider setting up Cloud Build for automated deployments:
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', '$_IMAGE_NAME', '.']
  
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', '$_IMAGE_NAME']
  
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'mansion-watch-scraper'
      - '--image=$_IMAGE_NAME'
      - '--region=asia-northeast1'
      - '--platform=managed'
```

## Rollback Procedure

To rollback to a previous version:
```bash
# List revisions
gcloud run revisions list --service mansion-watch-scraper

# Rollback to specific revision
gcloud run services update-traffic mansion-watch-scraper \
  --to-revision=mansion-watch-scraper-00001-abc \
  --region=asia-northeast1
```
```

This expanded documentation provides a more comprehensive guide for deploying and managing the service on Google Cloud Run, including best practices, security considerations, and operational procedures.