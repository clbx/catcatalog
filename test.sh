#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PASS=0
FAIL=0
WARN=0

run_clip() {
    local clip="$1"
    local frame_skip="$2"
    local expect="$3"  # "detect", "none", or "either"

    output=$(python cli/detect.py "$clip" --frame-skip "$frame_skip" 2>&1)
    has_detection=false
    if echo "$output" | grep -q "animal(s)"; then
        has_detection=true
    fi

    local name
    name="$(basename "$clip")"
    local result=""

    case "$expect" in
        detect)
            if $has_detection; then
                result="PASS"
                ((PASS++))
            else
                result="FAIL"
                ((FAIL++))
            fi
            ;;
        none)
            if $has_detection; then
                result="FAIL"
                ((FAIL++))
            else
                result="PASS"
                ((PASS++))
            fi
            ;;
        either)
            if $has_detection; then
                result="OK (detected)"
                ((WARN++))
            else
                result="OK (missed)"
                ((PASS++))
            fi
            ;;
    esac

    # extract detection count if present
    local count="0"
    if $has_detection; then
        count=$(echo "$output" | grep -o '[0-9]* animal' | head -1 | grep -o '[0-9]*')
    fi

    printf "  %-6s %-30s skip=%-2s  detections=%s\n" "[$result]" "$name" "$frame_skip" "$count"
}

echo "========================================"
echo " Cat Catalog Detection Test Suite"
echo "========================================"

for frame_skip in 1 2 4; do
    echo ""
    echo "--- Frame skip: $frame_skip ---"
    echo ""

    echo "Positives (expect detections):"
    for clip in clips/positives/*.mp4; do
        run_clip "$clip" "$frame_skip" "detect"
    done

    echo ""
    echo "Negatives (expect no detections):"
    for clip in clips/negatives/*.mp4; do
        run_clip "$clip" "$frame_skip" "none"
    done

    echo ""
    echo "Close enough (either is acceptable):"
    for clip in clips/negative-but-close-enough/*.mp4; do
        run_clip "$clip" "$frame_skip" "either"
    done
done

echo ""
echo "========================================"
echo " Results: $PASS passed, $FAIL failed, $WARN borderline"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
