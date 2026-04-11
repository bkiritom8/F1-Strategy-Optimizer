#!/bin/bash

# F1 Strategy Optimizer - Pipeline Push Helper
# Automates the "Desktop Clone & Push" workflow to bypass OneDrive mmap timeouts.

set -e

REPO_URL="https://github.com/bkiritom8/F1-Strategy-Optimizer.git"
BRANCH="pipeline"
PUSH_DIR="$HOME/Desktop/f1-push"
CURRENT_DIR=$(pwd)

echo "🚀 Starting pipeline push process..."

# 1. Cleanup old push directory if it exists
if [ -d "$PUSH_DIR" ]; then
    echo "🧹 Cleaning up old push directory..."
    rm -rf "$PUSH_DIR"
fi

# 2. Clone fresh repository
echo "⏳ Cloning $BRANCH branch to $PUSH_DIR..."
git clone --branch "$BRANCH" "$REPO_URL" "$PUSH_DIR"

# 3. Copy files from current repo to push repo
# We use rsync to copy only the tracked files and avoid .git directory conflicts
echo "📂 Synchronizing files..."
rsync -av --progress \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.venv' \
    --exclude='data/' \
    --exclude='pipeline/' \
    --exclude='.cursor/' \
    "$CURRENT_DIR/" "$PUSH_DIR/"

# 4. Commit and Push
cd "$PUSH_DIR"
echo "📝 Stage and commit..."
git add .
# Use a generic message or allow user to provide one
COMMIT_MSG=${1:-"Pipeline update: Observability hardening and 2026 data alignment"}
git commit -m "$COMMIT_MSG"

echo "⬆️ Pushing to GitHub..."
git push origin "$BRANCH"

# 5. Cleanup
cd "$CURRENT_DIR"
echo "🧹 Final cleanup..."
rm -rf "$PUSH_DIR"

echo "✅ Pipeline push complete!"
