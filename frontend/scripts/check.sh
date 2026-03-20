#!/usr/bin/env bash
# Frontend code quality checks: formatting (Prettier) + linting (ESLint)
set -e

FRONTEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$FRONTEND_DIR"

echo "=== Frontend Quality Checks ==="
echo ""

# Install deps if node_modules missing
if [ ! -d "node_modules" ]; then
  echo "Installing dependencies..."
  npm install --silent
  echo ""
fi

FAILED=0

echo "1. Prettier format check..."
if npx prettier --check "**/*.{js,html,css}"; then
  echo "   Formatting OK"
else
  echo "   Formatting issues found. Run 'npm run format' to fix."
  FAILED=1
fi

echo ""
echo "2. ESLint lint check..."
if npx eslint script.js; then
  echo "   Lint OK"
else
  FAILED=1
fi

echo ""
if [ $FAILED -eq 0 ]; then
  echo "All checks passed!"
else
  echo "Some checks failed. See output above."
  exit 1
fi
