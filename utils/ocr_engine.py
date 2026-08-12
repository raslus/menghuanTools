"""OCR 引擎共享模块

提供跨页面复用的 OCR 能力：
- RapidOCR 单例引擎（双重检查锁，所有页面共享同一实例）
- 窗口查找（find_window_by_title）
- 屏幕截图 + 图像预处理 + 文字识别（OCREngine）

抽取自 ghost_hunter_page.py，保持算法一致性。
"""

import ctypes
import os
import sys
import threading
from ctypes import wintypes

import cv2
import mss
import numpy as np

from utils.logger_setup import logger

# ---------------------------------------------------------------------------
# OCR 引擎单例（模块级，所有页面共享）
# ---------------------------------------------------------------------------
_ocr_engine = None
_engine_lock = threading.Lock()


def get_ocr_engine():
    """获取 OCR 引擎单例（双重检查锁）

    优先使用 RapidOCR（纯 CPU），失败时回退到 EasyOCR。
    返回 None 表示无可用引擎。
    """
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine

    with _engine_lock:
        if _ocr_engine is not None:
            return _ocr_engine

        try:
            from rapidocr_onnxruntime import RapidOCR
            logger.info("正在初始化 RapidOCR...")
            _ocr_engine = RapidOCR()
            logger.info("RapidOCR 初始化成功")
            return _ocr_engine
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"RapidOCR 初始化失败: {e}")

        try:
            import easyocr
            model_dir = _get_easyocr_model_dir()
            logger.info("正在初始化 EasyOCR (CPU 模式)...")
            _ocr_engine = easyocr.Reader(
                ['ch_sim', 'en'], gpu=False, model_storage_directory=model_dir
            )
            logger.info("EasyOCR 初始化成功")
            return _ocr_engine
        except ImportError:
            logger.warning("RapidOCR 和 EasyOCR 均未安装，OCR 不可用")
        except Exception as e:
            logger.error(f"EasyOCR 初始化失败: {e}")

        return None


def _get_easyocr_model_dir():
    """获取 EasyOCR 模型目录（适配开发/打包模式）"""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'models', 'easyocr')
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'models', 'easyocr'
    )


def is_rapidocr(engine):
    """判断引擎是否为 RapidOCR 实例"""
    if engine is None:
        return False
    try:
        from rapidocr_onnxruntime import RapidOCR
        return isinstance(engine, RapidOCR)
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Windows 窗口查找
# ---------------------------------------------------------------------------
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def find_window_by_title(substring: str):
    """查找标题包含指定文本的第一个可见窗口

    排除聊天窗口，优先选择标题以"梦幻西游"开头、尺寸≥800×600的主窗口。

    Args:
        substring: 窗口标题包含的文本（如"梦幻西游"）

    Returns:
        tuple: (window_title, (left, top, right, bottom)) 或 None
    """
    user32 = ctypes.windll.user32
    candidates = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_callback(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value
                if substring in title:
                    if "聊天窗口" in title or "聊天框" in title:
                        return True

                    window_rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(window_rect))

                    client_rect = wintypes.RECT()
                    user32.GetClientRect(hwnd, ctypes.byref(client_rect))

                    client_left_top = POINT(0, 0)
                    user32.ClientToScreen(hwnd, ctypes.byref(client_left_top))

                    client_right_bottom = POINT(client_rect.right, client_rect.bottom)
                    user32.ClientToScreen(hwnd, ctypes.byref(client_right_bottom))

                    left = client_left_top.x
                    top = client_left_top.y
                    right = client_right_bottom.x
                    bottom = client_right_bottom.y

                    if right - left < 100 or bottom - top < 100:
                        left = window_rect.left
                        top = window_rect.top
                        right = window_rect.right
                        bottom = window_rect.bottom

                    width = right - left
                    height = bottom - top

                    score = 0
                    if title.startswith("梦幻西游"):
                        score += 10
                    if "Online" in title or "online" in title:
                        score += 5
                    if width >= 800 and height >= 600:
                        score += 10
                    if "聊天" not in title and "聊天框" not in title:
                        score += 5

                    candidates.append({
                        "title": title,
                        "rect": (left, top, right, bottom),
                        "score": score,
                    })
        return True

    user32.EnumWindows(enum_callback, 0)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    logger.debug(
        f"找到 {len(candidates)} 个匹配窗口，最佳匹配: {best['title']} (分数: {best['score']})"
    )
    return (best["title"], best["rect"])


# ---------------------------------------------------------------------------
# OCREngine：截图 + 预处理 + 识别
# ---------------------------------------------------------------------------
class OCREngine:
    """OCR 引擎封装：屏幕截图、图像预处理、文字识别

    供答题器等需要 OCR 的页面使用。共享模块级 RapidOCR 单例。
    """

    def __init__(self):
        self.screen_capture = mss.MSS()
        self.monitor = self.screen_capture.monitors[1]

    def capture_screen_region(self, region=None):
        """截取屏幕区域

        Args:
            region: (left, top, right, bottom) 屏幕坐标，None 表示全屏

        Returns:
            BGR 格式的 numpy 数组
        """
        if region:
            monitor = {
                "top": region[1],
                "left": region[0],
                "width": region[2] - region[0],
                "height": region[3] - region[1],
            }
        else:
            monitor = self.monitor

        screenshot = self.screen_capture.grab(monitor)
        img = np.array(screenshot)

        # mss 返回 BGRA（4通道），转换为 BGR（3通道）供 OCR 使用
        if img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        return img

    def preprocess_image(self, img):
        """图像预处理（复用 ghost_hunter_page 验证的 pipeline）

        包含：放大 3× → 高斯模糊 → CLAHE 增强 → 拉普拉斯锐化 →
        自适应阈值 → OTSU → Canny 边缘 → 多颜色通道提取 → 形态学滤波
        """
        scale_factor = 3
        scaled = cv2.resize(img, None, fx=scale_factor, fy=scale_factor,
                            interpolation=cv2.INTER_CUBIC)
        blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced_gray = clahe.apply(gray)

        kernel_sharpen = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced_gray, -1, kernel_sharpen)

        adaptive1 = cv2.adaptiveThreshold(
            sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 15, 3
        )
        adaptive2 = cv2.adaptiveThreshold(
            sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 4
        )
        _, otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        edges = cv2.Canny(sharpened, 30, 100, apertureSize=3)
        edge_enhanced = cv2.bitwise_or(adaptive1, edges)

        gray_inverted = cv2.bitwise_not(gray)
        _, dark_text = cv2.threshold(gray_inverted, 150, 255, cv2.THRESH_BINARY)

        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        lower_red1 = np.array([0, 60, 60])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 60, 60])
        upper_red2 = np.array([180, 255, 255])
        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
        hsv_red = cv2.bitwise_or(mask_red1, mask_red2)

        lower_yellow = np.array([20, 100, 100])
        upper_yellow = np.array([40, 255, 255])
        hsv_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

        lower_green = np.array([40, 40, 40])
        upper_green = np.array([90, 255, 255])
        hsv_green = cv2.inRange(hsv, lower_green, upper_green)

        lower_orange = np.array([10, 100, 100])
        upper_orange = np.array([20, 255, 255])
        hsv_orange = cv2.inRange(hsv, lower_orange, upper_orange)

        red_channel = blurred[:, :, 2].astype(np.int16)
        green_channel = blurred[:, :, 1].astype(np.int16)
        blue_channel = blurred[:, :, 0].astype(np.int16)

        red_diff = cv2.absdiff(red_channel, green_channel) + cv2.absdiff(red_channel, blue_channel)
        rgb_red = np.where(red_diff > 40, 255, 0).astype(np.uint8)

        green_diff = cv2.absdiff(green_channel, red_channel) + cv2.absdiff(green_channel, blue_channel)
        rgb_green = np.where(green_diff > 40, 255, 0).astype(np.uint8)

        blue_diff = cv2.absdiff(blue_channel, red_channel) + cv2.absdiff(blue_channel, green_channel)
        rgb_blue = np.where(blue_diff > 40, 255, 0).astype(np.uint8)

        yellow_rgb_mask = (red_channel > 80) & (green_channel > 80) & (blue_channel < 60)
        yellow_rgb = np.where(yellow_rgb_mask, 255, 0).astype(np.uint8)

        color_text = cv2.bitwise_or(hsv_red, rgb_red)
        color_text = cv2.bitwise_or(color_text, hsv_yellow)
        color_text = cv2.bitwise_or(color_text, yellow_rgb)
        color_text = cv2.bitwise_or(color_text, hsv_green)
        color_text = cv2.bitwise_or(color_text, rgb_green)
        color_text = cv2.bitwise_or(color_text, hsv_orange)
        color_text = cv2.bitwise_or(color_text, rgb_blue)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        color_text = cv2.morphologyEx(color_text, cv2.MORPH_CLOSE, kernel, iterations=1)

        combined = cv2.bitwise_or(edge_enhanced, otsu)
        combined = cv2.bitwise_or(combined, adaptive2)
        combined = cv2.bitwise_or(combined, dark_text)
        combined = cv2.bitwise_or(combined, color_text)

        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        cleaned = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel2, iterations=1)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel2, iterations=1)

        _, final = cv2.threshold(cleaned, 128, 255, cv2.THRESH_BINARY)
        return final

    def recognize_text(self, region=None, preprocess=True):
        """识别屏幕区域文本

        Args:
            region: (left, top, right, bottom) 屏幕坐标，None 表示全屏
            preprocess: 是否进行图像预处理（默认 True）

        Returns:
            list[str]: 识别到的文本行列表（按位置从上到下、从左到右排序）
        """
        engine = get_ocr_engine()
        if engine is None:
            logger.warning("OCR 引擎不可用")
            return []

        img = self.capture_screen_region(region)
        if preprocess:
            img = self.preprocess_image(img)

        try:
            if is_rapidocr(engine):
                result, _ = engine(img)
                if not result:
                    return []
                # result: [[box, text, score], ...]
                # 按位置排序（从上到下、从左到右）
                sorted_result = sorted(
                    result,
                    key=lambda x: (x[0][0][1], x[0][0][0])
                )
                texts = [item[1] for item in sorted_result]
                logger.debug(f"OCR 识别结果: {texts}")
                return texts
            else:
                # EasyOCR
                result = engine.readtext(img)
                if not result:
                    return []
                sorted_result = sorted(result, key=lambda x: (x[0][0][1], x[0][0][0]))
                return [item[1] for item in sorted_result]
        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            return []

    def get_screen_size(self):
        """获取主显示器尺寸"""
        primary = self.screen_capture.monitors[1]
        return primary["width"], primary["height"]

    def close(self):
        """释放截图资源"""
        try:
            self.screen_capture.close()
        except Exception:
            pass
