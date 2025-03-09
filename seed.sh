#!/bin/bash
set -e

# Check environment
ENV=${ENV:-development}
if [ "$ENV" = "production" ]; then
    echo "Skipping database seed in production environment"
else
    echo "Waiting for MongoDB..."
    until python -c "
import sys
import os
import motor.motor_asyncio
from pymongo.server_api import ServerApi

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')

try:
    client = motor.motor_asyncio.AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        server_api=ServerApi('1')
    )
    client.admin.command('ping')
    sys.exit(0)
except Exception as e:
    print(f'Error connecting to MongoDB: {e}')
    sys.exit(1)
" 2>/dev/null; do
        echo "MongoDB unavailable - sleeping 2s"
        sleep 2
    done

    echo "MongoDB is up - executing seed script"
    python seed.py
fi

echo "Starting application..."
exec "$@"
