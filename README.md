# emotion_detector V13-2

ROS 2 Jazzy / Ubuntu 24.04 向けの **複数人対応・日本語感情表示デモ** です。  
USB カメラ映像を `/image_raw` で受け取り、顔ごとに **ID + 感情ラベル** を重畳した画像を
`/assist/image_annotated` に publish します。

この V13-2 は、V13 の**笑顔が悲しみに寄りやすい問題への判定改善**を維持しつつ、
重かった**性別推定と表示処理を削除**して軽量化した版です。

---

## 1. できること

- USB カメラ映像の取り込み
- 顔検出
- DeepFace による感情推定
- DeepFace の 7感情をそのまま扱う表示
- 日本語ラベル表示
- 複数人同時表示
- 人物ごとの簡易トラッキング ID 付与
- 枠線と表情名を同色表示

### 表示ラベル（DeepFace 7種類）
- happy
- neutral
- surprise
- angry
- sad
- fear
- disgust

### 画面表示ラベル（日本語）
- 喜び
- 無表情
- 驚き
- 怒り
- 悲しみ
- 恐れ
- 嫌悪

### 色
- 喜び: 緑
- 無表情: 青
- 驚き: 紫
- 怒り: 赤
- 悲しみ: 水色
- 恐れ: 黄
- 嫌悪: オレンジ

---

## 1-1. V10 ベースの安定方針

V8 / V9 では MediaPipe backend を使って顔検出品質を上げる方向を試しましたが、環境によっては

- 顔が検出されない
- 常に無表情になる
- 枠が一切出ない

という問題が起こり得ます。

そのため V10 以降では、**OpenCV Haar cascade で顔検出**し、**DeepFace で感情分類**する構成を採用しています。

1. **OpenCV Haar cascade** で顔検出
2. 検出した顔領域を multi-person tracking
3. 切り出した顔に対して `DeepFace.analyze(..., detector_backend="skip")`
4. DeepFace の 7感情をそのまま日本語表示

### 期待される効果
- 顔枠が安定して出やすい
- V9 よりトラブルが少ない
- DeepFace の 7感情表示は維持
- 実運用での動作確認がしやすい

---

## 1-2. V12 / V13 / V13-2 の判定改善

V11 では、DeepFace の `dominant_emotion` をほぼそのまま採用していました。  
そのため、**笑っていても「悲しみ」へ倒れる**ことがありました。

V12 / V13 / V13-2 では次のように調整しています。

1. `dominant_emotion` の直採用をやめ、**emotion スコア全体**で判定
2. **喜び (`happy`) をやや優遇**
3. **悲しみ (`sad`) は厳しめに判定**
4. あいまいなケースは **無表情** に倒す
5. 感情分類に使う顔領域を **少し広めに切り出し**、口元・頬の情報を取りやすくする

### 目的
- 「笑っているのに悲しみ」と出る誤判定の低減
- 自然な微笑みを喜びとして拾いやすくする
- 不安定な悲しみ判定を減らす

### V13 / V13-2 の追加修正
- V12 実行時の `IndentationError` を修正
- `infer_emotion()` の実装を整理し、正常起動できるように修正
- `gender` 推定とその画面表示を削除し、処理負荷を軽減

---

## 2. このアプリの安定構成

このアプリは **3ターミナル構成** で使うのが最も安定します。

- **ターミナル1**: detector ノード（venv 必須）
- **ターミナル2**: usb_cam ノード（system Python / ROS 環境）
- **ターミナル3**: rqt_image_view（system Python / ROS 環境）

### 理由
- detector は `DeepFace` と `TensorFlow` を使うため、**Python venv** が必要
- `rqt_image_view` は Qt 依存があるため、**venv を使わず system 側で起動**するほうが安定
- `usb_cam` はフォーマット相性があるため、**別ターミナルで明示起動**するほうがトラブルが少ない

---

## 3. ディレクトリ構成

この ZIP を展開すると、次の構成になります。

```text
emotion_ws/
  └─ src/
      └─ assist_detector/
          ├─ assist_detector/
          │   ├─ __init__.py
          │   └─ node.py
          ├─ launch/
          │   └─ assist_system.launch.py
          ├─ resource/
          │   └─ assist_detector
          ├─ scripts/
          │   └─ rewrite_shebang.sh
          ├─ package.xml
          ├─ setup.py
          ├─ setup.cfg
          └─ README.md
```

---

## 4. 必要環境

- Ubuntu 24.04
- ROS 2 Jazzy
- USB カメラ
- Python 3.12
- WSL2 の場合は USB カメラを WSL 側へ接続済みであること

---

## 5. apt 依存パッケージ

まず system 側に以下をインストールしてください。

```bash
sudo apt update
sudo apt install -y \
  python3-opencv \
  python3-pil \
  python3-yaml \
  fonts-noto-cjk \
  v4l-utils \
  ros-jazzy-cv-bridge \
  ros-jazzy-rqt-image-view \
  ros-jazzy-usb-cam
```

---

## 6. Python 仮想環境の作成

DeepFace は Ubuntu 24.04 では **venv 利用を推奨**します。

`assist_detector` は venv 内で `DeepFace` を使いつつ、ROS 2 の `rclpy` / `cv_bridge` と
system 側の `cv2` / `PIL` も参照するため、**必ず system site packages を有効にした venv** を作ってください。

```bash
cd ~
rm -rf ~/emotion_venv
python3 -m venv --system-site-packages ~/emotion_venv
source ~/emotion_venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install deepface tf-keras
```

### NumPy について重要
`cv_bridge` との相性のため、**NumPy は 1.26.4 を使用**してください。

```bash
pip uninstall -y numpy
pip install numpy==1.26.4
```

### DeepFace import 確認
```bash
source /opt/ros/jazzy/setup.bash
python -c "import cv2, PIL, yaml, rclpy, cv_bridge; from deepface import DeepFace; import numpy; print('DeepFace OK'); print('numpy', numpy.__version__)"
```

期待:
- `DeepFace` が import OK
- `numpy` が `1.26.4`
- `cv2` / `PIL` / `yaml` / `rclpy` / `cv_bridge` も import OK

---

## 7. ZIP の展開

```bash
cd ~
unzip ~/Downloads/emotion_detector_V13.zip
```

展開後:

```bash
cd ~/emotion_ws
```

---

## 8. ビルド

### 重要
**venv を有効にした状態で build してください。**

```bash
cd ~/emotion_ws
source ~/emotion_venv/bin/activate
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

### build 後の注意
`colcon build --symlink-install` をやり直すと、`assist_detector_node` の shebang が
`/usr/bin/python3` に戻ることがあります。  
その場合は detector 起動前に、必ず次の「9. shebang 修正」を再実行してください。

---

## 9. shebang 修正（重要）

ROS 2 の `ament_python` パッケージでは、環境によっては生成された実行ファイルの shebang が
`/usr/bin/python3` になることがあります。  
その場合、DeepFace が見えず `DeepFace not available` になります。

この ZIP には修正スクリプトを同梱しています。  
**build 後に必ず 1 回実行してください。**

```bash
cd ~/emotion_ws
bash ~/emotion_ws/src/assist_detector/scripts/rewrite_shebang.sh
```

### 確認
```bash
head -n 1 ~/emotion_ws/install/assist_detector/lib/assist_detector/assist_detector_node
```

期待:
```bash
#!/home/<ユーザー名>/emotion_venv/bin/python
```

`#!/usr/bin/python3` のままなら、その状態では `DeepFace` が見えず、
実行時に感情が `無表情` に寄りやすくなります。

---

## 10. 起動手順（成功実績あり）

### ターミナル1: detector
```bash
cd ~/emotion_ws
source ~/emotion_venv/bin/activate
source /opt/ros/jazzy/setup.bash
bash ~/emotion_ws/src/assist_detector/scripts/rewrite_shebang.sh
head -n 1 ~/emotion_ws/install/assist_detector/lib/assist_detector/assist_detector_node
source ~/emotion_ws/install/setup.bash
ros2 launch assist_detector assist_system.launch.py
```

正常なら次のようなログが出ます。

```text
DeepFace backend enabled
assist_detector V13 started
```

`DeepFace backend enabled` が出ない場合は、そのまま進めず shebang を確認してください。

---

### ターミナル2: usb_cam
```bash
cd ~/emotion_ws
source /opt/ros/jazzy/setup.bash
ros2 run usb_cam usb_cam_node_exe --ros-args \
  -p video_device:=/dev/video0 \
  -p image_width:=640 \
  -p image_height:=480 \
  -p framerate:=15.0 \
  -p pixel_format:=mjpeg2rgb \
  -p io_method:=mmap \
  -r __node:=usb_cam
```

### 重要
この環境では、以下は失敗しやすいです。

- `pixel_format:=mjpeg` → **ドライバ未対応**
- `pixel_format:=yuyv` → **Select timeout になることがある**

このため、**`mjpeg2rgb` を使用**してください。

---

### ターミナル3: 画像表示
```bash
cd ~
export XDG_RUNTIME_DIR=/tmp/runtime-$USER
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
source /opt/ros/jazzy/setup.bash
ros2 run rqt_image_view rqt_image_view
```

`/assist/image_annotated` を選択してください。

---

## 11. 動作確認コマンド

### 入力画像が来ているか
```bash
source /opt/ros/jazzy/setup.bash
ros2 topic list | grep image
ros2 topic echo --once /image_raw
```

### detector が出力しているか
```bash
source /opt/ros/jazzy/setup.bash
ros2 topic info -v /assist/image_annotated
ros2 topic echo --once /assist/image_annotated
```

### detector ノードの接続確認
```bash
source /opt/ros/jazzy/setup.bash
ros2 node info /assist_detector
```

### detector 起動ログ確認
```bash
source /opt/ros/jazzy/setup.bash
ros2 node list
```

期待:
- `/assist_detector` が見える
- detector 起動端末に `DeepFace backend enabled` が出ている

---

## 12. WSL2 を使う場合の手順

### 12-1. USB カメラを WSL 側へ接続
Windows 側で `usbipd-win` を利用して、カメラを WSL に attach してください。  
Windows 管理者 PowerShell 例:

```powershell
usbipd list
usbipd bind --busid <BUSID>
usbipd attach --wsl --busid <BUSID>
```

WSL 側で確認:

```bash
ls -l /dev/video0
```

### 12-2. GUI を使う
Windows 11 + WSLg の場合は、そのまま `rqt_image_view` が起動できることがあります。  
表示されない場合は X11 / WSLg / DISPLAY 設定を確認してください。

### 12-3. WSL2 で camera が不安定な場合
WSL2 では `usb_cam` のフォーマット相性が出やすいです。  
この ZIP で採用している成功構成は次です。

```bash
-p pixel_format:=mjpeg2rgb
-p io_method:=mmap
-p image_width:=640
-p image_height:=480
-p framerate:=15.0
```

### 12-4. Docker を併用する場合
Docker コンテナにカメラを渡す場合は `/dev/video0` をデバイスマウントしてください。

例:
```bash
docker run --rm -it \
  --device=/dev/video0:/dev/video0 \
  --net=host \
  <image>
```

ただし、今回の成功構成は **WSL 上の Ubuntu で直接 `usb_cam` を起動**する形です。  
まずはこの README の手順どおりに WSL Ubuntu 上で成功させてください。

---

## 13. 既知の注意点

### 13-1. `DeepFace not available` が出る
原因:
- shebang が `/usr/bin/python3` になっている

対処:
```bash
cd ~/emotion_ws
source ~/emotion_venv/bin/activate
source /opt/ros/jazzy/setup.bash
bash ~/emotion_ws/src/assist_detector/scripts/rewrite_shebang.sh
head -n 1 ~/emotion_ws/install/assist_detector/lib/assist_detector/assist_detector_node
```

期待:
```bash
#!/home/<ユーザー名>/emotion_venv/bin/python
```

その後に detector を再起動:
```bash
source ~/emotion_ws/install/setup.bash
ros2 launch assist_detector assist_system.launch.py
```

### 13-1-1. 常に `無表情` になる
原因の第一候補:
- `DeepFace` が実際には読めていない
- detector 起動時に `DeepFace backend enabled` が出ていない
- shebang が `/usr/bin/python3` に戻っている

確認:
```bash
head -n 1 ~/emotion_ws/install/assist_detector/lib/assist_detector/assist_detector_node
source ~/emotion_venv/bin/activate
python -c "from deepface import DeepFace; print('DeepFace OK')"
```

対処:
```bash
bash ~/emotion_ws/src/assist_detector/scripts/rewrite_shebang.sh
```

### 13-2. `No module named yaml`
対処:
```bash
source ~/emotion_venv/bin/activate
pip install PyYAML
```

### 13-3. `rqt_image_view` が `PyQt5` エラーになる
原因:
- venv を有効化したまま `rqt_image_view` を起動している

対処:
- `rqt_image_view` は **system 側**で起動

```bash
source /opt/ros/jazzy/setup.bash
ros2 run rqt_image_view rqt_image_view
```

### 13-3-1. `rqt_image_view` で `FileNotFoundError: os.getcwd()` が出る
原因:
- 削除済みディレクトリや無効なカレントディレクトリにいる
- `XDG_RUNTIME_DIR` が未設定

対処:
```bash
cd ~
export XDG_RUNTIME_DIR=/tmp/runtime-$USER
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
source /opt/ros/jazzy/setup.bash
ros2 run rqt_image_view rqt_image_view
```

### 13-4. `/image_raw` が流れない
原因:
- `usb_cam` が落ちている
- フォーマット指定不一致

対処:
- README の成功コマンドをそのまま使う
- `mjpeg2rgb` を使う

### 13-5. 顔枠が表示されない
原因:
- 顔が小さい
- 顔が暗い
- 正面顔でない
- Haar cascade で検出されていない

対処:
- 顔を中央に大きく映す
- 明るい場所で試す
- 正面顔で試す

---

## 14. この V13 の仕様

- 顔の上に `ID + 感情` を表示
- 例: `ID1 喜び`
- DeepFace の 7感情を個別に表示
- 複数人同時表示対応
- 人物ごとに履歴を持つ
- 簡易トラッキング方式
- OpenCV Haar cascade で顔検出
- DeepFace で感情分類
- V12 の笑顔優遇ロジックを維持
- 上部タイトルなし
- 下部一覧なし

### 制約
- 人が大きく交差すると ID が入れ替わることがある
- 一度画面外へ出て戻ると別 ID になることがある
- 厳密な再識別ではない
- Haar cascade のため、斜め顔や小さい顔には弱いことがある
- DeepFace の出力は環境や表情の弱さによって揺れることがあるため、短い履歴で平滑化しています

---

## 15. 使い方まとめ（最短）

### 初回のみ
```bash
sudo apt update
sudo apt install -y \
  python3-opencv python3-pil python3-yaml fonts-noto-cjk v4l-utils \
  ros-jazzy-cv-bridge ros-jazzy-rqt-image-view ros-jazzy-usb-cam

python3 -m venv ~/emotion_venv
source ~/emotion_venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install deepface tf-keras PyYAML
pip uninstall -y numpy
pip install numpy==1.26.4

cd ~
unzip ~/Downloads/emotion_detector_V13.zip
cd ~/emotion_ws
source ~/emotion_venv/bin/activate
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
bash ~/emotion_ws/src/assist_detector/scripts/rewrite_shebang.sh
```

### 毎回
#### ターミナル1
```bash
cd ~/emotion_ws
source ~/emotion_venv/bin/activate
source /opt/ros/jazzy/setup.bash
source ~/emotion_ws/install/setup.bash
ros2 launch assist_detector assist_system.launch.py
```

#### ターミナル2
```bash
cd ~/emotion_ws
source /opt/ros/jazzy/setup.bash
ros2 run usb_cam usb_cam_node_exe --ros-args \
  -p video_device:=/dev/video0 \
  -p image_width:=640 \
  -p image_height:=480 \
  -p framerate:=15.0 \
  -p pixel_format:=mjpeg2rgb \
  -p io_method:=mmap \
  -r __node:=usb_cam
```

#### ターミナル3
```bash
cd ~/emotion_ws
source /opt/ros/jazzy/setup.bash
ros2 run rqt_image_view rqt_image_view
```

`/assist/image_annotated` を選択してください。
