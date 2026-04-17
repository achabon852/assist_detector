# assist_detector

ROS 2 Jazzy / Ubuntu 24.04 向けの感情推定ノードです。USB カメラ映像の顔領域を検出し、DeepFace を使って感情を推定し、日本語ラベル付きの画像を `/assist/image_annotated` に publish します。

## Features

- OpenCV Haar cascade による顔検出
- DeepFace による感情推定
- 複数人の簡易トラッキング
- 日本語ラベルと色付きバウンディングボックス表示
- `/image_raw` を入力、`/assist/image_annotated` を出力

## Environment

- Ubuntu 24.04
- ROS 2 Jazzy
- Python 3.12
- USB カメラ

## System Dependencies

```bash
sudo apt update
sudo apt install -y \
  opencv-data \
  python3-opencv \
  python3-pil \
  python3-yaml \
  fonts-noto-cjk \
  v4l-utils \
  ros-jazzy-cv-bridge \
  ros-jazzy-rqt-image-view \
  ros-jazzy-usb-cam
```

## Python Environment

DeepFace は仮想環境で動かす前提です。`rclpy` や `cv_bridge` も使うため、`--system-site-packages` を付けた venv を使います。

```bash
cd ~
python3 -m venv --system-site-packages ~/emotion_venv
source ~/emotion_venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install deepface tf-keras numpy==1.26.4
```

動作確認:

```bash
source /opt/ros/jazzy/setup.bash
source ~/emotion_venv/bin/activate
python -c "import cv2, PIL, yaml, rclpy, cv_bridge; from deepface import DeepFace; import numpy; print('DeepFace OK'); print('numpy', numpy.__version__)"
```

## Build

ワークスペースのルートでビルドします。

```bash
cd ~/emotion_ws
source /opt/ros/jazzy/setup.bash
source ~/emotion_venv/bin/activate
colcon build --packages-select assist_detector
bash src/assist_detector/scripts/rewrite_shebang.sh
source install/setup.bash
```

OpenCV の Haar cascade が見つからない場合は、先に `opencv-data` を入れてください。

```bash
sudo apt install -y opencv-data
```

## Run

3 ターミナルに分けると安定して動かしやすいです。

ターミナル 1: detector

```bash
cd ~/emotion_ws
source /opt/ros/jazzy/setup.bash
source ~/emotion_venv/bin/activate
source install/setup.bash
ros2 run assist_detector assist_detector_node
```

起動直後に `DeepFace backend enabled` と出ることを確認してください。出ない場合は次を実行してから再起動します。

```bash
cd ~/emotion_ws
source ~/emotion_venv/bin/activate
bash src/assist_detector/scripts/rewrite_shebang.sh
```

ターミナル 2: usb_cam

```bash
source /opt/ros/jazzy/setup.bash
ros2 run usb_cam usb_cam_node_exe --ros-args \
  -p video_device:=/dev/video0 \
  -p image_width:=640 \
  -p image_height:=480 \
  -p framerate:=15.0 \
  -p pixel_format:=mjpeg2rgb \
  -p io_method:=mmap
```

`pixel_format:=yuyv` は環境によって `Select timeout` で落ちることがあります。その場合は `mjpeg2rgb` を使ってください。

ターミナル 3: viewer

```bash
source /opt/ros/jazzy/setup.bash
ros2 run rqt_image_view rqt_image_view
```

`rqt_image_view` では `/assist/image_annotated` を選択します。

## Topics

- Subscribe: `/image_raw`
- Publish: `/assist/image_annotated`

## Emotion Labels

DeepFace の 7 感情を日本語で表示します。

- `happy` -> `喜び`
- `neutral` -> `無表情`
- `surprise` -> `驚き`
- `angry` -> `怒り`
- `sad` -> `悲しみ`
- `fear` -> `恐れ`
- `disgust` -> `嫌悪`

## Repository Layout

```text
assist_detector/
├── assist_detector/
│   ├── __init__.py
│   └── node.py
├── launch/
│   └── assist_system.launch.py
├── resource/
│   └── assist_detector
├── scripts/
│   └── rewrite_shebang.sh
├── package.xml
├── README.md
├── setup.cfg
└── setup.py
```
