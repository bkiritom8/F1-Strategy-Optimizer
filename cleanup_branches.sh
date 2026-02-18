#!/bin/bash
# Run this after merging the PR on GitHub

echo "Fetching latest changes..."
git fetch origin

echo "Switching to main..."
git checkout main

echo "Pulling latest main..."
git pull origin main

echo "Deleting local feature branches..."
git branch -d claude/cross-platform-python-setup-Apsdv 2>/dev/null || true
git branch -d claude/final-merge-main-Apsdv 2>/dev/null || true

echo "Deleting remote feature branches..."
git push origin --delete claude/cross-platform-python-setup-Apsdv 2>/dev/null || true
git push origin --delete claude/final-merge-main-Apsdv 2>/dev/null || true

echo ""
echo "Cleanup complete! Remaining branches:"
git branch -a

echo ""
echo "You are now on the main branch with all changes merged."
