```sh
docker build -f mansion_watch_scraper/pubsub/Dockerfile.job -t asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-batch-job:latest .
```

```sh
docker tag asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-batch-job:latest asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-batch-job:latest
```

```sh
docker push asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-batch-job:latest
```

```sh
gcloud run jobs update mansion-watch-batch-job --image asia-northeast1-docker.pkg.dev/daring-night-451212-a8/mansion-watch/mansion-watch-batch-job:latest --region asia-northeast1 --memory 512Mi --cpu 1000m --max-retries 3 --task-timeout 10m | cat
```

## Run the job
```sh
gcloud run jobs execute mansion-watch-batch-job --region asia-northeast1 | cat
```
