#!/bin/bash

# ========== SETTINGS ==========
OUTPUT_DIR="/media/RAW"
BASE_NAME="compression_test_$(date +%Y-%m-%d_%H-%M-%S)"
SRC="/dev/mmcblk0"
TEST_SIZE_MB=1024
BS="4M"
LOG_FILE="$OUTPUT_DIR/${BASE_NAME}.log"
CSV_FILE="$OUTPUT_DIR/${BASE_NAME}.csv"
TMP_IMG="/dev/shm/tmp_test.img"  # Uses RAM for pxz

mkdir -p "$OUTPUT_DIR"
echo "Compression test started at $(date)" | tee "$LOG_FILE"
echo "Method,Seconds,Output Size (MB),Output File" > "$CSV_FILE"

# ========== HELPER ==========
run_test() {
  local label="$1"
  local cmd="$2"
  local outfile="$3"

  echo -e "\n=== $label ===" | tee -a "$LOG_FILE"
  echo "Command: $cmd" | tee -a "$LOG_FILE"
  START=$(date +%s)
  eval "$cmd"
  END=$(date +%s)
  SECONDS=$((END - START))

  if [ -f "$outfile" ]; then
    FILESIZE=$(du -m "$outfile" | cut -f1)
    echo "$label,$SECONDS,$FILESIZE,$outfile" >> "$CSV_FILE"
    echo "$label took $SECONDS sec, size: ${FILESIZE} MB" | tee -a "$LOG_FILE"
  else
    echo "$label failed or no output file found" | tee -a "$LOG_FILE"
    echo "$label,FAILED,0,$outfile" >> "$CSV_FILE"
  fi
}

# ========== TESTS ==========

# xz -3
run_test "xz -3" \
  "sudo head -c ${TEST_SIZE_MB}M $SRC | pv | xz -3 -c > $OUTPUT_DIR/${BASE_NAME}_xz3.img.xz" \
  "$OUTPUT_DIR/${BASE_NAME}_xz3.img.xz"

# pixz
if command -v pixz >/dev/null; then
  run_test "pixz" \
    "sudo head -c ${TEST_SIZE_MB}M $SRC | pv | pixz > $OUTPUT_DIR/${BASE_NAME}_pixz.img.xz" \
    "$OUTPUT_DIR/${BASE_NAME}_pixz.img.xz"
else
  echo "Skipping pixz (not installed)" | tee -a "$LOG_FILE"
fi

# pxz -T4 (requires temp file)
if command -v pxz >/dev/null; then
  echo "Creating 1 GiB RAM-based image for pxz..." | tee -a "$LOG_FILE"
  sudo head -c ${TEST_SIZE_MB}M "$SRC" > "$TMP_IMG"
  run_test "pxz -T4" \
    "pxz -T4 $TMP_IMG && mv $TMP_IMG.xz $OUTPUT_DIR/${BASE_NAME}_pxzT4.img.xz" \
    "$OUTPUT_DIR/${BASE_NAME}_pxzT4.img.xz"
else
  echo "Skipping pxz (not installed)" | tee -a "$LOG_FILE"
fi

# zstd -3
if command -v zstd >/dev/null; then
  run_test "zstd -3" \
    "sudo head -c ${TEST_SIZE_MB}M $SRC | pv | zstd -3 -T0 -o $OUTPUT_DIR/${BASE_NAME}_zstd3.img.zst" \
    "$OUTPUT_DIR/${BASE_NAME}_zstd3.img.zst"
else
  echo "Skipping zstd (not installed)" | tee -a "$LOG_FILE"
fi

# lz4
if command -v lz4 >/dev/null; then
  run_test "lz4" \
    "sudo head -c ${TEST_SIZE_MB}M $SRC | pv | lz4 - $OUTPUT_DIR/${BASE_NAME}_lz4.img.lz4" \
    "$OUTPUT_DIR/${BASE_NAME}_lz4.img.lz4"
else
  echo "Skipping lz4 (not installed)" | tee -a "$LOG_FILE"
fi

# ========== CLEANUP ==========
[ -f "$TMP_IMG" ] && sudo rm -f "$TMP_IMG"

echo -e "\nAll tests completed."
echo "Log: $LOG_FILE"
echo "CSV: $CSV_FILE"
