#!/bin/bash

# Set the base URL
BASE_URL="http://localhost:8081"

# Create a mock JWT token for local testing
# In production, this would be a real service account token
MOCK_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkNsb3VkIFJ1biBJbnZva2VyIiwiaWF0IjoxNTE2MjM5MDIyfQ.L8i6g3PfcHlioHCCPURC9pmXT7gdJpx3kOVB2q4SOy4"

# Function to create a base64 encoded message
create_message() {
  local data=$1
  echo -n "$data" | base64
}

# Function to send request
send_request() {
  local data=$1
  curl -X POST "${BASE_URL}/" \
    -H "Authorization: Bearer ${MOCK_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "X-CloudPubSub-DeliveryAttempt: 1" \
    -d "$data"
  echo -e "\n"
}

echo "Starting message format tests..."
echo "----------------------------------------"

# Test 1: Basic health check
echo "Test 1: Basic health check (GET)..."
curl -X GET "${BASE_URL}/"
echo -e "\n----------------------------------------\n"

# Test 2: Batch processing (all users)
echo "Test 2: Batch processing for all users..."
data='{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","check_only":true}'
message='{
    "message": {
        "data": "'$(create_message "$data")'",
        "messageId": "batch-all-users",
        "publishTime": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")'",
        "attributes": {}
    },
    "subscription": "projects/test-project/subscriptions/test-subscription"
}'
send_request "$message"
echo "----------------------------------------"

# Test 3: Batch processing (specific user)
echo "Test 3: Batch processing for specific user..."
data='{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}'
message='{
    "message": {
        "data": "'$(create_message "$data")'",
        "messageId": "batch-specific-user",
        "publishTime": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")'",
        "attributes": {}
    },
    "subscription": "projects/test-project/subscriptions/test-subscription"
}'
send_request "$message"
echo "----------------------------------------"

# Test 4: Invalid message format
echo "Test 4: Invalid message format..."
send_request '{"invalid": "format"}'
echo "----------------------------------------"

# Test 5: Invalid base64 data
echo "Test 5: Invalid base64 data..."
message='{
    "message": {
        "data": "invalid-base64",
        "messageId": "invalid-data",
        "publishTime": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")'",
        "attributes": {}
    },
    "subscription": "projects/test-project/subscriptions/test-subscription"
}'
send_request "$message"
echo "----------------------------------------"

# Test 6: Specific property update
echo "Test 6: Specific property update..."
data='{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","url":"https://suumo.jp/ms/chuko/tokyo/sc_104/nc_95274249/","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}'
message='{
    "message": {
        "data": "'$(create_message "$data")'",
        "messageId": "specific-property",
        "publishTime": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")'",
        "attributes": {}
    },
    "subscription": "projects/test-project/subscriptions/test-subscription"
}'
send_request "$message"
echo "----------------------------------------"

# Test 7: Library property update
echo "Test 7: Library property update..."
data='{"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'","url":"https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_76395792/","line_user_id":"U8e5f5a15df59714a88334bfb9f8ff106","check_only":true}'
message='{
    "message": {
        "data": "'$(create_message "$data")'",
        "messageId": "library-property",
        "publishTime": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")'",
        "attributes": {}
    },
    "subscription": "projects/test-project/subscriptions/test-subscription"
}'
send_request "$message"
echo "----------------------------------------"

echo "All tests completed!"
