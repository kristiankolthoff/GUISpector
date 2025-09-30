#!/bin/sh

# Wait for MySQL to be ready
while ! nc -z "$DATABASE_HOST" 3306; do
  echo "Waiting for MySQL..."
  sleep 1
done

# Run migrations  
python /app/webapp/manage.py migrate

# Start Daphne
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application