Specific property with check_only and for a specific user
```sh
curl -X POST "https://mansion-watch-scraper-bb7aa35h5q-an.a.run.app/" -H "Content-Type: application/json" -H "Authorization: Bearer $(gcloud auth print-identity-token)" -d '{"message":{"data":"'$(echo '{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","url":"https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_76395793/","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}' | base64)'","messageId":"test-message-'$(date +%s)'","publishTime":"'$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")'","attributes":{}},"subscription":"projects/daring-night-451212-a8/subscriptions/mansion-watch-scraper-sub-push"}' | cat
```

Batch processing for a specific user
```sh
curl -X POST "https://mansion-watch-scraper-bb7aa35h5q-an.a.run.app/" -H "Content-Type: application/json" -H "Authorization: Bearer $(gcloud auth print-identity-token)" -d '{"message":{"data":"'$(echo '{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}' | base64)'","messageId":"test-message-'$(date +%s)'","publishTime":"'$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")'","attributes":{}},"subscription":"projects/daring-night-451212-a8/subscriptions/mansion-watch-scraper-sub-push"}' | cat
```
