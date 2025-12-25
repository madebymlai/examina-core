#!/bin/bash
# Rebrand: qupled → qupled
set -e

# Directories to skip
EXCLUDE_DIRS=(".git" "node_modules" "__pycache__" ".venv" "venv" ".next" "dist" "build" ".pytest_cache" ".mypy_cache" "*.egg-info" "uv.lock")

EXCLUDE_PATTERN=""
for dir in "${EXCLUDE_DIRS[@]}"; do
    EXCLUDE_PATTERN="$EXCLUDE_PATTERN -path '*/$dir' -prune -o -path '*/$dir/*' -prune -o"
done

echo "Scanning for files containing 'qupled'..."
FILES=$(eval "find . $EXCLUDE_PATTERN -type f -print" | xargs grep -l -i "qupled" 2>/dev/null || true)

if [[ -z "$FILES" ]]; then
    echo "No files found containing 'qupled'"
    exit 0
fi

FILE_COUNT=$(echo "$FILES" | wc -l)
echo "Found $FILE_COUNT files to update"
echo ""

for file in $FILES; do
    if file "$file" | grep -q "binary"; then
        continue
    fi

    sed -i \
        -e 's/qupled-cloud/qupled-cloud/g' \
        -e 's/qupled-cli/qupled-cli/g' \
        -e 's/qupled-core/qupled-core/g' \
        -e 's/qupled/qupled/g' \
        -e 's/Qupled/Qupled/g' \
        -e 's/QUPLED/QUPLED/g' \
        "$file"
    echo "  Updated: $file"
done

echo ""
echo "=== REBRAND COMPLETE ==="
