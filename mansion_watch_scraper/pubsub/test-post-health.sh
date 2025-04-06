#!/bin/bash

# Set the base URL
BASE_URL="http://localhost:8081"

# Test 0: Basic health check (GET)
echo "Testing basic health check..."
curl -X GET "${BASE_URL}/"

echo -e "\n\n"

# Test 1: Run batch processing for all users (checks active properties with check_only) which happens when running a batch job
echo "Testing batch processing for all users..."
echo "This will:"
echo "- Filter for properties with is_active=true"
echo "- Send messages with check_only=true"
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{
  "message": {
    "data": "'$(echo -n '{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","check_only":true}' | base64)'",
    "messageId": "batch-all-users"
  }
}'

echo -e "\n\n"

# # Test 2: Run batch processing for specific user (checks active properties with check_only) which happens when the user clicks the "Update All" button on the UI
echo "Testing batch processing for specific user..."
echo "This will:"
echo "- Filter for properties with is_active=true"
echo "- Filter for specific line_user_id"
echo "- Send messages with check_only=true"
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{
  "message": {
    "data": "'$(echo -n '{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}' | base64)'",
    "messageId": "batch-specific-user"
  }
}'

echo -e "\n\n"

# Test 3: Test with invalid user ID
echo "Testing with invalid user ID..."
echo "This will process the message but the service will handle the invalid user"
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{
  "message": {
    "data": "'$(echo -n '{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","line_user_id":"invalid_user_id","check_only":true}' | base64)'",
    "messageId": "invalid-user"
  }
}'

echo -e "\n\n"

# Test 4: Test invalid JSON payload
echo "Testing invalid JSON payload..."
echo "Expected: 400 Bad Request - Invalid JSON payload"
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{invalid json'

echo -e "\n\n"

# Test 5: Test missing request body
echo "Testing missing request body..."
echo "Expected: 400 Bad Request - Missing message field"
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{}'

echo -e "\n\n"

# Test 6: Test missing message field
echo "Testing missing message field..."
echo "Expected: 400 Bad Request - Missing message field"
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{"not_message": {}}'

echo -e "\n\n"

# Test 7: Test invalid base64 data
echo "Testing invalid base64 data..."
echo "Expected: 500 Error - Invalid base64 data"
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{
  "message": {
    "data": "invalid-base64",
    "messageId": "invalid-data"
  }
}'

echo -e "\n\n"

# Test 8: Test specific property update
echo "Testing specific property update..."
curl -X POST "${BASE_URL}/" \
  -H "Content-Type: application/json" \
  -d '{
  "message": {
    "data": "'$(echo -n '{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","url":"https://suumo.jp/ms/chuko/tokyo/sc_104/nc_95274249/","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}' | base64)'",
    "messageId": "specific-property"
  }
}'
