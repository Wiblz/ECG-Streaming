#!/bin/bash
# Bump version across all packages

set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 0.2.0"
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

echo "✓ Version bumped to $NEW_VERSION"
echo ""
echo "Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Commit: git commit -am 'Bump version to $NEW_VERSION'"
echo "  3. Tag: git tag v$NEW_VERSION"
echo "  4. Push: git push && git push --tags"
