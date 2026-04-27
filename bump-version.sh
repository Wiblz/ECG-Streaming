#!/bin/bash
# Bump version across all packages, commit, and tag

set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 0.5.0"
    exit 1
fi

NEW_VERSION="$1"

echo "Bumping version to $NEW_VERSION..."

# Update version in ecg-common/version.py (single source of truth)
sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" packages/ecg-common/src/ecg_common/version.py

# Update version in workspace pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Update version in each package pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" packages/ecg-common/pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" packages/ecg-collector/pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" packages/ecg-aggregator/pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" packages/ecg-simulator/pyproject.toml

# Update version in frontend package.json
sed -i "s/\"version\": \".*\"/\"version\": \"$NEW_VERSION\"/" frontend/package.json

echo "✓ Version bumped to $NEW_VERSION"

# Commit and tag (only version files, nothing else from the index)
git commit \
    packages/ecg-common/src/ecg_common/version.py \
    pyproject.toml \
    packages/ecg-common/pyproject.toml \
    packages/ecg-collector/pyproject.toml \
    packages/ecg-aggregator/pyproject.toml \
    packages/ecg-simulator/pyproject.toml \
    frontend/package.json \
    -m "Bump version to $NEW_VERSION"
git tag "v$NEW_VERSION"

echo "✓ Committed and tagged v$NEW_VERSION"
echo ""
echo "Push with:"
echo "  git push && git push --tags"
