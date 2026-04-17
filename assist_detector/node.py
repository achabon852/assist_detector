import os
import time
from collections import Counter, deque
from dataclasses import dataclass, field

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from PIL import Image as PILImage, ImageDraw, ImageFont
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except Exception:
    DeepFace = None
    DEEPFACE_AVAILABLE = False


def _find_font() -> str:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""


def _find_cascade() -> str:
    candidates = [
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
    ]
    try:
        if hasattr(cv2, "data"):
            candidates.insert(0, cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception:
        pass
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("haarcascade_frontalface_default.xml not found")


@dataclass
class Track:
    track_id: int
    bbox: tuple
    history: deque
    last_label: str
    last_age: int | None = None
    label_started_at: float = 0.0
    last_scores: dict = field(default_factory=dict)
    miss_count: int = 0
    infer_interval: int = 3
    seen_count: int = 0


class EmotionDetector(Node):
    def __init__(self):
        super().__init__("assist_detector")
        self.bridge = CvBridge()
        # Align image topics with usb_cam and image viewers that use sensor-data QoS.
        self.sub = self.create_subscription(Image, "/image_raw", self.cb, qos_profile_sensor_data)
        self.pub = self.create_publisher(Image, "/assist/image_annotated", qos_profile_sensor_data)

        self.face = cv2.CascadeClassifier(_find_cascade())
        font_path = _find_font()
        self.font = ImageFont.truetype(font_path, 28) if font_path else ImageFont.load_default()
        self.small_font = ImageFont.truetype(font_path, 16) if font_path else ImageFont.load_default()

        self.label_colors = {
            "喜び": (0, 180, 0),
            "無表情": (0, 90, 255),
            "驚き": (160, 0, 180),
            "怒り": (220, 0, 0),
            "悲しみ": (0, 200, 255),
            "恐れ": (220, 220, 0),
            "嫌悪": (255, 140, 0),
        }

        self.tracks = {}
        self.next_track_id = 1
        self.max_miss = 10
        self.match_distance = 90.0
        self.deepface_warning_logged = False

        if DEEPFACE_AVAILABLE:
            self.get_logger().info("DeepFace backend enabled")
        else:
            self.get_logger().warning("DeepFace not available. Check venv / shebang / dependencies")

        self.get_logger().info("assist_detector V13-2 started")

    def map_label(self, emotion: str) -> str:
        mapping = {
            "happy": "喜び",
            "neutral": "無表情",
            "surprise": "驚き",
            "angry": "怒り",
            "sad": "悲しみ",
            "fear": "恐れ",
            "disgust": "嫌悪",
        }
        return mapping.get(emotion, "無表情")

    def default_scores(self):
        return {
            "happy": 0.0,
            "neutral": 100.0,
            "surprise": 0.0,
            "angry": 0.0,
            "sad": 0.0,
            "fear": 0.0,
            "disgust": 0.0,
        }

    def smooth_label(self, track: Track, label: str) -> str:
        track.history.append(label)
        counts = Counter(track.history)
        return counts.most_common(1)[0][0]

    @staticmethod
    def _center(bbox):
        x, y, w, h = bbox
        return (x + w / 2.0, y + h / 2.0)

    @staticmethod
    def _size(bbox):
        x, y, w, h = bbox
        return w * h

    def _bbox_distance(self, a, b):
        ax, ay = self._center(a)
        bx, by = self._center(b)
        center_dist = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
        area_a = max(1.0, self._size(a))
        area_b = max(1.0, self._size(b))
        area_ratio = max(area_a, area_b) / min(area_a, area_b)
        penalty = (area_ratio - 1.0) * 20.0
        return center_dist + penalty

    def update_tracks(self, detections):
        updated = set()
        assigned = {}

        for track in self.tracks.values():
            track.miss_count += 1

        for det in detections:
            best_id = None
            best_score = 1e9
            for tid, track in self.tracks.items():
                if tid in updated:
                    continue
                score = self._bbox_distance(det, track.bbox)
                if score < best_score:
                    best_score = score
                    best_id = tid

            if best_id is not None and best_score < self.match_distance:
                track = self.tracks[best_id]
                track.bbox = det
                track.miss_count = 0
                track.seen_count += 1
                updated.add(best_id)
                assigned[best_id] = det
            else:
                tid = self.next_track_id
                self.next_track_id += 1
                self.tracks[tid] = Track(
                    track_id=tid,
                    bbox=det,
                    history=deque(maxlen=3),
                    last_label="無表情",
                    last_age=None,
                    label_started_at=time.monotonic(),
                    last_scores=self.default_scores(),
                    miss_count=0,
                    seen_count=1,
                )
                updated.add(tid)
                assigned[tid] = det

        stale = [tid for tid, track in self.tracks.items() if track.miss_count > self.max_miss]
        for tid in stale:
            del self.tracks[tid]

        return assigned

    def infer_emotion(self, face_bgr):
        if not DEEPFACE_AVAILABLE:
            return "無表情", self.default_scores(), None

        try:
            rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            result = DeepFace.analyze(
                img_path=rgb,
                actions=["emotion", "age"],
                detector_backend="skip",
                enforce_detection=False,
                silent=True,
            )
            if isinstance(result, list):
                result = result[0]

            age_value = result.get("age")
            age = int(round(float(age_value))) if age_value is not None else None

            emotions = result.get("emotion", {})
            if not emotions:
                emotion = result.get("dominant_emotion", "neutral")
                scores = self.default_scores()
                scores[emotion] = 100.0
                if emotion != "neutral":
                    scores["neutral"] = 0.0
                return self.map_label(emotion), scores, age

            scores = {
                "happy": float(emotions.get("happy", 0.0)),
                "neutral": float(emotions.get("neutral", 0.0)),
                "surprise": float(emotions.get("surprise", 0.0)),
                "angry": float(emotions.get("angry", 0.0)),
                "sad": float(emotions.get("sad", 0.0)),
                "fear": float(emotions.get("fear", 0.0)),
                "disgust": float(emotions.get("disgust", 0.0)),
            }

            happy = scores["happy"]
            neutral = scores["neutral"]
            surprise = scores["surprise"]
            angry = scores["angry"]
            sad = scores["sad"]
            fear = scores["fear"]
            disgust = scores["disgust"]

            # DeepFace が sad に寄るケースを強く抑えるため、sad は大きめに減点して扱う。
            adjusted_scores = {
                "happy": happy + 10.0,
                "neutral": neutral + 6.0,
                "surprise": surprise + 8.0,
                "angry": angry + 3.0,
                "sad": max(0.0, sad - 22.0),
                "fear": fear + 6.0,
                "disgust": disgust + 6.0,
            }

            adjusted_top = max(adjusted_scores, key=adjusted_scores.get)
            adjusted_top_score = adjusted_scores[adjusted_top]

            if happy >= 12.0 and adjusted_scores["happy"] >= adjusted_scores["sad"] - 2.0:
                return "喜び", scores, age
            if surprise >= 12.0 and adjusted_scores["surprise"] >= adjusted_scores["sad"]:
                return "驚き", scores, age
            if neutral >= 18.0 and adjusted_scores["neutral"] >= adjusted_scores["sad"]:
                return "無表情", scores, age
            if fear >= 10.0 and adjusted_scores["fear"] >= adjusted_scores["sad"]:
                return "恐れ", scores, age
            if disgust >= 10.0 and adjusted_scores["disgust"] >= adjusted_scores["sad"]:
                return "嫌悪", scores, age
            if angry >= 14.0 and adjusted_scores["angry"] >= adjusted_scores["sad"]:
                return "怒り", scores, age
            if sad >= 55.0 and sad >= happy + 20.0 and sad >= neutral + 18.0 and sad >= surprise + 18.0:
                return "悲しみ", scores, age

            dominant = result.get("dominant_emotion", "neutral")
            if dominant == "happy" and happy >= 10.0:
                return "喜び", scores, age
            if dominant == "surprise" and surprise >= 10.0:
                return "驚き", scores, age
            if dominant == "fear" and fear >= 10.0:
                return "恐れ", scores, age
            if dominant == "disgust" and disgust >= 10.0:
                return "嫌悪", scores, age
            if dominant == "angry" and angry >= 12.0:
                return "怒り", scores, age
            if dominant == "neutral" and neutral >= 16.0:
                return "無表情", scores, age
            if dominant == "sad" and sad >= 60.0 and sad >= happy + 22.0 and sad >= neutral + 18.0:
                return "悲しみ", scores, age

            return self.map_label(adjusted_top if adjusted_top_score >= 12.0 else "neutral"), scores, age
        except Exception as e:
            if not self.deepface_warning_logged:
                self.get_logger().warning(f"DeepFace inference failed once: {e}")
                self.deepface_warning_logged = True
            return "無表情", self.default_scores(), None

    def draw_label(self, frame_bgr, rect, label, track_id, duration_sec, scores, age):
        x, y, w, h = rect
        color = self.label_colors.get(label, (0, 90, 255))
        text = f"ID{track_id} {label}（{duration_sec:.1f}s）"
        score_x = x + 8
        score_lines = [
            f"喜び {scores.get('happy', 0.0):4.1f}%",
            f"驚き {scores.get('surprise', 0.0):4.1f}%",
            f"怒り {scores.get('angry', 0.0):4.1f}%",
            f"悲しみ {scores.get('sad', 0.0):4.1f}%",
            f"恐れ {scores.get('fear', 0.0):4.1f}%",
            f"嫌悪 {scores.get('disgust', 0.0):4.1f}%",
            f"無表情 {scores.get('neutral', 0.0):4.1f}%",
        ]

        pil = PILImage.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=2)
        text_y = max(0, y - 34)
        draw.text((x, text_y), text, font=self.font, fill=color)
        text_bbox = draw.textbbox((x, text_y), text, font=self.font)

        info_lines = []
        if age is not None:
            info_lines.append(f"推定年齢{age}歳")

        if info_lines:
            line_bboxes = [draw.textbbox((0, 0), line, font=self.small_font) for line in info_lines]
            info_width = max(bbox[2] - bbox[0] for bbox in line_bboxes)
            line_height = max(bbox[3] - bbox[1] for bbox in line_bboxes)
            info_x = max(0, x + w - info_width - 6)
            info_y = min(max(0, y + 4), max(0, frame_bgr.shape[0] - (line_height * len(info_lines)) - 4))
            for i, line in enumerate(info_lines):
                line_y = info_y + i * line_height
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                    draw.text((info_x + dx, line_y + dy), line, font=self.small_font, fill=(0, 0, 0))
                draw.text((info_x, line_y), line, font=self.small_font, fill=(255, 255, 255))

        score_y = text_bbox[3] + 2
        if score_y + len(score_lines) * 18 > frame_bgr.shape[0]:
            score_y = min(frame_bgr.shape[0] - len(score_lines) * 18 - 4, y + h + 4)
        for i, line in enumerate(score_lines):
            line_y = max(0, score_y + i * 18)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                draw.text((score_x + dx, line_y + dy), line, font=self.small_font, fill=(0, 0, 0))
            draw.text((score_x, line_y), line, font=self.small_font, fill=(255, 255, 255))
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    def cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            self.get_logger().error(f"cv_bridge conversion failed: {e}")
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(60, 60)
        )
        detections = [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

        assigned = self.update_tracks(detections)
        annotated = frame.copy()

        for tid, bbox in assigned.items():
            x, y, w, h = bbox

            pad_x = int(w * 0.12)
            pad_y = int(h * 0.18)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(frame.shape[1], x + w + pad_x)
            y2 = min(frame.shape[0], y + h + pad_y)

            face_bgr = frame[y1:y2, x1:x2]
            if face_bgr.size == 0:
                continue

            track = self.tracks[tid]
            if track.seen_count % track.infer_interval == 0:
                raw_label, scores, age = self.infer_emotion(face_bgr)
                smoothed_label = self.smooth_label(track, raw_label)
                if smoothed_label != track.last_label:
                    track.label_started_at = time.monotonic()
                track.last_label = smoothed_label
                track.last_scores = scores
                track.last_age = age

            duration_sec = max(0.0, time.monotonic() - track.label_started_at)
            annotated = self.draw_label(
                annotated,
                bbox,
                track.last_label,
                tid,
                duration_sec,
                track.last_scores,
                track.last_age,
            )

        out = self.bridge.cv2_to_imgmsg(annotated, "bgr8")
        out.header = msg.header
        self.pub.publish(out)


def main():
    rclpy.init()
    node = EmotionDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()
