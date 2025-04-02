#!/bin/bash

# Set the base URL
BASE_URL="http://localhost:8081"

# Test 0: Basic health check (GET)
echo "Testing basic health check..."
curl -X GET "${BASE_URL}/health"

echo -e "\n\n"

# Test 1: Run batch processing for all users (checks active properties with check_only) which happens when running a batch job
echo "Testing batch processing for all users..."
echo "This will:"
echo "- Filter for properties with is_active=true"
echo "- Send messages with check_only=true"
curl -X POST "${BASE_URL}/batch" \
  -H "Content-Type: application/json" \
  -d '{}'

echo -e "\n\n"

# # Test 2: Run batch processing for specific user (checks active properties with check_only) which happens when the user clicks the "Update All" button on the UI
echo "Testing batch processing for specific user..."
echo "This will:"
echo "- Filter for properties with is_active=true"
echo "- Filter for specific line_user_id"
echo "- Send messages with check_only=true"
curl -X POST "${BASE_URL}/batch" \
  -H "Content-Type: application/json" \
  -d '{
  "line_user_id": "U8e5f5a15df59714a88334bfb9f8ff106"
}'

echo -e "\n\n"

# Test 3: Test with invalid user ID
echo "Testing with invalid user ID..."
echo "This will return a 404 error without processing properties"
curl -X POST "${BASE_URL}/batch" \
  -H "Content-Type: application/json" \
  -d '{
  "line_user_id": "invalid_user_id"
}'

echo -e "\n\n"

# Test 4: Test invalid JSON payload
echo "Testing invalid JSON payload..."
echo "Expected: 400 Bad Request - Invalid JSON payload"
curl -X POST "${BASE_URL}/batch" \
  -H "Content-Type: application/json" \
  -d '{invalid json'

echo -e "\n\n"

# Test 5: Test missing request body
echo "Testing missing request body..."
echo "Expected: 400 Bad Request - Missing request body"
curl -X POST "${BASE_URL}/batch" \
  -H "Content-Type: application/json"

echo -e "\n\n"

# Test 6: Test malformed headers
echo "Testing malformed headers..."
echo "Expected: 400 Bad Request - Content-Type must be application/json"
curl -X POST "${BASE_URL}/batch" \
  -H "Content-Type: text/plain" \
  -d '{}'

echo -e "\n\n"

# Test 7: Test wrong content type
echo "Testing wrong content type..."
echo "Expected: 400 Bad Request - Content-Type must be application/json"
curl -X POST "${BASE_URL}/batch" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d '{}'

echo -e "\n\n"

# Test 8: Test Pub/Sub message to /health
echo "Testing Pub/Sub message to /health..."
curl -X POST "${BASE_URL}/health" \
  -H "Content-Type: application/json" \
  -d '{
  "message": {
    "data": "'$(echo -n '{"timestamp":"2024-04-02T10:00:00Z","url":"https://suumo.jp/ms/chuko/tokyo/sc_104/nc_95274249/","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}' | base64)'",
    "messageId": "test-message-id"
  }
}'
