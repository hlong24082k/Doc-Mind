#! /bin/bash
# Script to run the server application
echo "Starting the server..."

export PYTHONPATH=$(pwd)/src:$PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1

python server.py
