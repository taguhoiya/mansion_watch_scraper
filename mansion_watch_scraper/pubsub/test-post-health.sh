# First, create the message data and encode it in base64
echo '{
  "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
  "url": "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_77039606/",
  "line_user_id": "U8e5f5a15df59714a88334bfb9f8ff106",
  "check_only": true
}' | base64

# Generate a unique message ID using timestamp
message_id="test-$(date +%s)"

# Then use the base64 output in your request
# NOTE: Change `check_only` if you want to not only check but also scrape/store the property
curl -X POST http://localhost:8081/health \
    -H "Content-Type: application/json" \
    -d '{
  "message": {
    "data": "'$(echo '{
      "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
      "url": "https://suumo.jp/ms/chuko/kanagawa/sc_kawasakishinakahara/nc_77039606/",
      "line_user_id": "U8e5f5a15df59714a88334bfb9f8ff106",
      "check_only": true
    }' | base64)'",
    "messageId": "'$message_id'",
    "publishTime": "2024-04-01T12:00:00Z"
  }
}'
