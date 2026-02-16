#!/bin/bash
set -e

echo "RigBooks Starting..."

if [ ! -f "data/rigbooks.db" ]; then
    echo "First run - running migration..."
    python3 execution/migrate_to_sqlite.py
else
    echo "Database exists - skipping migration"
fi

echo "Launching Streamlit..."
exec streamlit run app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    --server.fileWatcherType=none
