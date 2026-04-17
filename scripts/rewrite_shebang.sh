#!/usr/bin/env bash
set -euo pipefail

TARGET="${HOME}/emotion_ws/install/assist_detector/lib/assist_detector/assist_detector_node"
PYTHON_PATH="${HOME}/emotion_venv/bin/python"

if [ ! -f "$TARGET" ]; then
  echo "ERROR: $TARGET が見つかりません。先に colcon build --symlink-install を実行してください。"
  exit 1
fi

if [ ! -x "$PYTHON_PATH" ]; then
  echo "ERROR: $PYTHON_PATH が見つかりません。先に ~/emotion_venv を作成してください。"
  exit 1
fi

sed -i "1s|^#!.*|#!${PYTHON_PATH}|" "$TARGET"
echo "Updated shebang:"
head -n 1 "$TARGET"
