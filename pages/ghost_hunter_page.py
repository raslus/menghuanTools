import flet as ft
import cv2
import numpy as np
import mss
import pyautogui
import re
import threading
import time
import json
import os
import sys
import urllib.request
import requests
from PIL import Image as PILImage
from utils.platform_utils import get_app_data_dir
from utils.logger_setup import logger

try:
    from rapidocr_onnxruntime import RapidOCR
    _rapidocr_available = True
except ImportError:
    _rapidocr_available = False

try:
    import easyocr
    _easyocr_available = True
except ImportError:
    _easyocr_available = False

import ctypes
from ctypes import wintypes


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def find_window_by_title(substring: str):
    """查找标题包含指定文本的第一个可见窗口

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
                    
                    is_main = False
                    score = 0
                    
                    if title.startswith("梦幻西游"):
                        score += 10
                    if "Online" in title or "online" in title:
                        score += 5
                    if width >= 800 and height >= 600:
                        score += 10
                        is_main = True
                    if "聊天" not in title and "聊天框" not in title:
                        score += 5
                    
                    candidates.append({
                        "title": title,
                        "rect": (left, top, right, bottom),
                        "score": score,
                        "is_main": is_main,
                    })
        return True

    user32.EnumWindows(enum_callback, 0)
    
    if not candidates:
        return None
    
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    best = candidates[0]
    logger.debug(f"找到{len(candidates)}个匹配窗口，最佳匹配: {best['title']} (分数: {best['score']})")
    return (best["title"], best["rect"])


class CoordinateOCR:
    _ocr_engine = None
    _engine_lock = threading.Lock()

    def __init__(self):
        self.screen_capture = mss.MSS()
        self.monitor = self.screen_capture.monitors[1]
        self.ocr = None
        self._ocr_initialized = False
        self._model_dir = None
        self.custom_region = None       # 自定义截取区域 (left, top, right, bottom)
        self.locked_window_title = None  # 锁定的窗口标题
        self.map_panel_region = None     # 地图面板区域 (left, top, right, bottom)
        self.ghost_task_region = None    # 抓鬼任务区域 (left, top, right, bottom)
        self._setup_model_dir()

    def _setup_model_dir(self):
        if getattr(sys, 'frozen', False):
            self._model_dir = os.path.join(os.path.dirname(sys.executable), 'models', 'easyocr')
        else:
            self._model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'easyocr')
        logger.debug(f"模型目录: {self._model_dir}")

    def set_window_region(self, region, window_title=None):
        """设置自定义截取区域，锁定后OCR只在该区域内识别

        Args:
            region: (left, top, right, bottom) 屏幕坐标区域
            window_title: 窗口标题（用于显示）
        """
        self.custom_region = region
        self.locked_window_title = window_title
        logger.info(f"OCR区域已锁定: {region}, 窗口: {window_title}")

    def clear_window_region(self):
        """清除自定义截取区域，恢复全屏识别"""
        self.custom_region = None
        self.locked_window_title = None
        logger.info("OCR区域锁定已清除")

    def is_window_locked(self):
        """检查是否已锁定窗口区域"""
        return self.custom_region is not None

    def _init_ocr(self):
        if self._ocr_initialized:
            return

        if CoordinateOCR._ocr_engine is not None:
            self.ocr = CoordinateOCR._ocr_engine
            self._ocr_initialized = True
            logger.debug("复用已初始化的OCR引擎")
            return

        with CoordinateOCR._engine_lock:
            if CoordinateOCR._ocr_engine is not None:
                self.ocr = CoordinateOCR._ocr_engine
                self._ocr_initialized = True
                return

            if _rapidocr_available:
                try:
                    logger.info("正在初始化RapidOCR...")
                    CoordinateOCR._ocr_engine = RapidOCR()
                    self.ocr = CoordinateOCR._ocr_engine
                    self._ocr_initialized = True
                    logger.info("RapidOCR初始化成功")
                except Exception as e:
                    logger.error(f"RapidOCR初始化失败: {e}")

            if not self._ocr_initialized and _easyocr_available:
                try:
                    logger.info("正在初始化EasyOCR (CPU模式)...")
                    CoordinateOCR._ocr_engine = easyocr.Reader(['ch_sim', 'en'], gpu=False, model_storage_directory=self._model_dir)
                    self.ocr = CoordinateOCR._ocr_engine
                    self._ocr_initialized = True
                    logger.info("EasyOCR初始化成功")
                except Exception as e:
                    logger.error(f"EasyOCR初始化失败: {e}")

    def capture_screen_region(self, region=None):
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
        
        if img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        
        return img

    def preprocess_image(self, img):
        scale_factor = 3
        
        scaled = cv2.resize(img, None, fx=scale_factor, fy=scale_factor, 
                           interpolation=cv2.INTER_CUBIC)
        
        blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
        
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
        
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced_gray = clahe.apply(gray)
        
        kernel_sharpen = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced_gray, -1, kernel_sharpen)
        
        adaptive1 = cv2.adaptiveThreshold(sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 15, 3)
        adaptive2 = cv2.adaptiveThreshold(sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY_INV, 21, 4)
        
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
        red_mask = red_diff > 40
        rgb_red = np.where(red_mask, 255, 0).astype(np.uint8)
        
        green_diff = cv2.absdiff(green_channel, red_channel) + cv2.absdiff(green_channel, blue_channel)
        green_mask = green_diff > 40
        rgb_green = np.where(green_mask, 255, 0).astype(np.uint8)
        
        blue_diff = cv2.absdiff(blue_channel, red_channel) + cv2.absdiff(blue_channel, green_channel)
        blue_mask = blue_diff > 40
        rgb_blue = np.where(blue_mask, 255, 0).astype(np.uint8)
        
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

    def get_screen_size(self):
        primary_monitor = self.screen_capture.monitors[1]
        return primary_monitor["width"], primary_monitor["height"]

    MAP_NAMES = [
        "建邺城", "东海湾", "江南野外", "长安城", "大唐国境", "大唐境外",
        "长寿村", "长寿郊外", "傲来国", "花果山", "月宫", "大唐官府",
        "方寸山", "化生寺", "女儿村", "魔王寨", "狮陀岭", "地府", "盘丝洞",
        "龙宫", "天宫", "五庄观", "普陀山", "境外", "西梁女国", "无名城"
    ]

    GHOST_KEYWORDS = ["鬼", "钟馗", "捉鬼", "抓鬼", "任务", "领取"]

    CHAR_REPLACEMENTS = {
        "O": "0", "o": "0", "Q": "0",
        "I": "1", "l": "1", "i": "1",
        "Z": "2", "z": "2",
        "S": "5", "s": "5",
        "B": "8",
    }

    def _correct_text(self, text):
        corrected = []
        for char in text:
            corrected.append(self.CHAR_REPLACEMENTS.get(char, char))
        return "".join(corrected)

    def _levenshtein_distance(self, s1, s2):
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    cost = 0
                else:
                    cost = 1
                dp[i][j] = min(
                    dp[i-1][j] + 1,
                    dp[i][j-1] + 1,
                    dp[i-1][j-1] + cost
                )
        
        return dp[m][n]

    def _fuzzy_match_map_name(self, text):
        if not text:
            return None
        
        cleaned = re.sub(r'[\[\]\(\)\d,.，。、\s]', '', text)
        
        candidates = []
        for i in range(len(cleaned)):
            for j in range(i + 2, min(i + 6, len(cleaned) + 1)):
                candidates.append(cleaned[i:j])
        
        best_match = None
        min_distance = float('inf')
        
        for map_name in self.MAP_NAMES:
            for candidate in candidates:
                distance = self._levenshtein_distance(candidate, map_name)
                similarity = 1 - distance / max(len(candidate), len(map_name))
                
                if distance < min_distance and similarity > 0.5:
                    min_distance = distance
                    best_match = map_name
        
        if min_distance <= 2 and best_match:
            logger.debug(f"模糊匹配地图名: '{text}' -> '{best_match}'")
            return best_match
        return None

    def _split_coordinate(self, num_str):
        """智能分割合并的坐标数字（如7396 -> (73, 96)）"""
        length = len(num_str)
        
        if length == 4:
            x = int(num_str[:2])
            y = int(num_str[2:])
            if x <= 255 and y <= 255:
                return (x, y)
        
        if length == 3:
            x = int(num_str[:1])
            y = int(num_str[1:])
            if x <= 255 and y <= 255:
                return (x, y)
            
            x = int(num_str[:2])
            y = int(num_str[2:])
            if x <= 255 and y <= 255:
                return (x, y)
        
        if length == 5:
            x = int(num_str[:2])
            y = int(num_str[2:])
            if x <= 255 and y <= 255:
                return (x, y)
            
            x = int(num_str[:3])
            y = int(num_str[3:])
            if x <= 255 and y <= 255:
                return (x, y)
        
        return None

    def _is_ghost_hunting_text(self, text):
        for keyword in self.GHOST_KEYWORDS:
            if keyword in text:
                return True
        return False

    def recognize_coordinates(self, search_region=None):
        if not _rapidocr_available and not _easyocr_available:
            logger.warning("RapidOCR和EasyOCR均未安装，无法进行文字识别")
            return None
    
        self._init_ocr()
        if self.ocr is None:
            logger.error("OCR初始化失败")
            return None
    
        def _merge_texts_by_coords(raw_results):
            if not raw_results:
                return []
            
            sorted_results = sorted(raw_results, key=lambda x: (x[0][0][1], x[0][0][0]))
            
            if len(sorted_results) == 1:
                return [sorted_results[0][1]]
            
            y_centers = []
            for item in sorted_results:
                bbox = item[0]
                center_y = (bbox[0][1] + bbox[2][1]) / 2
                y_centers.append(center_y)
            
            gaps = []
            for i in range(1, len(y_centers)):
                gaps.append(y_centers[i] - y_centers[i-1])
            
            if len(gaps) == 1:
                all_texts = [item[1] for item in sorted_results]
                return ["".join(all_texts)]
            
            avg_gap = sum(gaps) / len(gaps)
            std_gap = (sum((g - avg_gap)**2 for g in gaps) / len(gaps)) ** 0.5
            
            group_indices = [0]
            for i in range(len(gaps)):
                if abs(gaps[i] - avg_gap) > std_gap * 1.5:
                    group_indices.append(i + 1)
            
            group_indices.append(len(sorted_results))
            
            merged_lines = []
            for i in range(len(group_indices) - 1):
                start = group_indices[i]
                end = group_indices[i + 1]
                group_items = sorted_results[start:end]
                group_items.sort(key=lambda x: x[0][0][0])
                merged_text = "".join([item[1] for item in group_items])
                merged_lines.append(merged_text)
            
            return merged_lines
        
        def ocr_image(img, region_desc):
            texts = []
            try:
                if _rapidocr_available and isinstance(self.ocr, RapidOCR):
                    logger.debug(f"{region_desc} 调用RapidOCR识别...")
                    
                    if img.ndim == 3 and img.shape[2] == 4:
                        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                    elif img.ndim == 3 and img.shape[2] == 3:
                        pass
                    else:
                        logger.warning(f"{region_desc} 图像格式异常: {img.shape}")
                    
                    result, _ = self.ocr(img)
                    logger.debug(f"{region_desc} RapidOCR原始结果: {result}")
                    if result and len(result) > 0:
                        texts = _merge_texts_by_coords(result)
                    logger.debug(f"{region_desc} OCR识别结果(合并后): {texts}")
                else:
                    result = self.ocr.readtext(img)
                    if result and len(result) > 0:
                        for line in result:
                            if len(line) > 1:
                                texts.append(line[1])
                    logger.debug(f"{region_desc} OCR识别结果: {texts}")
            except Exception as e:
                logger.error(f"{region_desc} OCR识别异常: {e}")
            return texts
        
        try:
            all_text = ""
            
            if self.custom_region:
                map_region = None
                if self.map_panel_region:
                    map_region = self.map_panel_region
                else:
                    window_left, window_top, window_right, window_bottom = self.custom_region
                    map_panel_width = 220
                    map_panel_height = 85
                    map_region = (
                        window_left,
                        window_top,
                        window_left + map_panel_width,
                        window_top + map_panel_height
                    )
                
                img = self.capture_screen_region(map_region)
                logger.debug(f"地图面板区域截图: {map_region}")
                
                texts = ocr_image(img, "地图面板")
                if not texts:
                    processed_img = self.preprocess_image(img)
                    texts = ocr_image(processed_img, "地图面板(预处理)")
                
                all_text = " ".join(texts)

                if self.ghost_task_region:
                    img = self.capture_screen_region(self.ghost_task_region)
                    logger.debug(f"抓鬼任务区域截图: {self.ghost_task_region}")
                    
                    texts = ocr_image(img, "抓鬼任务")
                    if not texts:
                        processed_img = self.preprocess_image(img)
                        texts = ocr_image(processed_img, "抓鬼任务(预处理)")
                    
                    all_text += " " + " ".join(texts)

            else:
                screen_width, screen_height = self.get_screen_size()
                
                if search_region:
                    img = self.capture_screen_region(search_region)
                    logger.debug(f"搜索区域截图: {search_region}")
                else:
                    map_panel_width = 220
                    map_panel_height = 85
                    map_region = (0, 0, map_panel_width, map_panel_height)
                    img = self.capture_screen_region(map_region)
                    logger.debug(f"左上角地图面板区域截图: {map_region}")
    
                texts = ocr_image(img, "地图面板")
                if not texts:
                    processed_img = self.preprocess_image(img)
                    texts = ocr_image(processed_img, "地图面板(预处理)")
                
                all_text = " ".join(texts)
    
            if not all_text.strip():
                logger.debug("未识别到任何文字")
                return None
            
            corrected_text = self._correct_text(all_text)
            if corrected_text != all_text:
                logger.debug(f"文本修正: '{all_text}' -> '{corrected_text}'")
            all_text = corrected_text
    
            map_name = self._extract_map_name(all_text)
            is_ghost_hunting = self._is_ghost_hunting_text(all_text)
            
            pattern = r'(\d{1,3})\s*[,.，。、]\s*(\d{1,3})'
            match = re.search(pattern, all_text)
            
            if not match:
                pattern2 = r'(\d{1,3})\s+(\d{1,3})'
                match = re.search(pattern2, all_text)
            
            coords = None
            
            if not match and map_name:
                bracket_pattern = r'\[(\d{3,5})\]'
                bracket_match = re.search(bracket_pattern, all_text)
                if bracket_match:
                    num_str = bracket_match.group(1)
                    coords = self._split_coordinate(num_str)
            
            if coords:
                if is_ghost_hunting:
                    result_data = {
                        "type": "ghost",
                        "coords": coords,
                        "map_name": map_name,
                        "text": all_text
                    }
                    logger.info(f"识别到抓鬼任务: {map_name} ({coords[0]}, {coords[1]})")
                else:
                    result_data = {
                        "type": "position",
                        "coords": coords,
                        "map_name": map_name,
                        "text": all_text
                    }
                    logger.info(f"识别到当前位置: {map_name} ({coords[0]}, {coords[1]})")
                
                return result_data
            
            if map_name:
                return {
                    "type": "position",
                    "coords": None,
                    "map_name": map_name,
                    "text": all_text
                }
    
            logger.debug("未识别到坐标和地图")
            return None
    
        except Exception as e:
            logger.error(f"OCR识别异常: {e}")
            return None

    def _extract_map_name(self, text):
        for map_name in self.MAP_NAMES:
            if map_name in text:
                return map_name
        
        special_patterns = [
            (r'(长寿).*(村|郊)', '长寿村'),
            (r'(建邺).*(城|镇)', '建邺城'),
            (r'(长安).*(城)', '长安城'),
            (r'(大唐).*(国境|境外)', '大唐国境'),
            (r'(东海).*(湾)', '东海湾'),
            (r'(江南).*(野外)', '江南野外'),
            (r'(傲来).*(国)', '傲来国'),
            (r'(花果).*(山)', '花果山'),
            (r'(女儿).*(村)', '女儿村'),
            (r'(普陀).*(山)', '普陀山'),
            (r'(五庄).*(观)', '五庄观'),
            (r'(方寸).*(山)', '方寸山'),
            (r'(天宫)', '天宫'),
            (r'(龙宫)', '龙宫'),
            (r'(地府)', '地府'),
            (r'(盘丝).*(洞)', '盘丝洞'),
            (r'(狮陀).*(岭)', '狮陀岭'),
            (r'(魔王).*(寨)', '魔王寨'),
            (r'(化生).*(寺)', '化生寺'),
            (r'(大唐).*(官府)', '大唐官府'),
            (r'(月宫)', '月宫'),
        ]
        
        for pattern, name in special_patterns:
            if re.search(pattern, text):
                return name
        
        fuzzy_match = self._fuzzy_match_map_name(text)
        if fuzzy_match:
            logger.debug(f"模糊匹配地图名: '{text}' -> '{fuzzy_match}'")
            return fuzzy_match
        
        return None


class GhostCoordinatePredictor:
    def __init__(self):
        self.learning_data = {}
        self._load_learning_data()
        
        self.map_rules = {
            "五庄观": {"x_less": True, "y_less": True},
            "普陀山": {"x_less": True, "y_less": True},
            "境外": {"x_less": False, "y_less": None},
        }

    def _load_learning_data(self):
        data_dir = get_app_data_dir()
        self.learning_file = os.path.join(data_dir, "ghost_hunter_learning.json")
        if os.path.exists(self.learning_file):
            try:
                with open(self.learning_file, 'r', encoding='utf-8') as f:
                    self.learning_data = json.load(f)
            except:
                self.learning_data = {}

    def _save_learning_data(self):
        try:
            with open(self.learning_file, 'w', encoding='utf-8') as f:
                json.dump(self.learning_data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def get_position_info(self, x, y, map_name=""):
        return {
            "type": "position",
            "center_x": x,
            "center_y": y,
            "x_min": x - 5,
            "x_max": x + 5,
            "y_min": y - 5,
            "y_max": y + 5,
            "radius_x": 5,
            "radius_y": 5,
            "map_name": map_name,
        }

    def predict_range(self, fake_x, fake_y, map_name=""):
        base_radius = 30
        
        if map_name in self.learning_data:
            stats = self.learning_data[map_name]
            avg_offset_x = stats.get("avg_offset_x", 0)
            avg_offset_y = stats.get("avg_offset_y", 0)
            std_dev_x = stats.get("std_dev_x", 15)
            std_dev_y = stats.get("std_dev_y", 15)
            
            adjusted_x = fake_x + avg_offset_x
            adjusted_y = fake_y + avg_offset_y
            
            confidence_factor = min(stats.get("count", 0) * 0.05, 0.5)
            radius_x = max(8, min(30, std_dev_x * (1.0 - confidence_factor)))
            radius_y = max(8, min(30, std_dev_y * (1.0 - confidence_factor)))
        else:
            adjusted_x = fake_x
            adjusted_y = fake_y
            radius_x = base_radius
            radius_y = base_radius

        rules = self.map_rules.get(map_name, {})
        
        small_map = map_name in ["五庄观", "普陀山"]
        
        if fake_x <= 50 and fake_y <= 50:
            x_min = max(0, fake_x - 30)
            x_max = fake_x
            y_min = max(0, fake_y - 30)
            y_max = fake_y
        elif fake_x >= 150 and fake_y >= 150:
            x_min = fake_x
            x_max = min(255, fake_x + 30)
            y_min = fake_y
            y_max = min(255, fake_y + 30)
        elif fake_x <= 50 and fake_y >= 150:
            x_min = max(0, fake_x - 30)
            x_max = fake_x
            y_min = fake_y
            y_max = min(255, fake_y + 30)
        elif fake_x >= 150 and fake_y <= 50:
            x_min = fake_x
            x_max = min(255, fake_x + 30)
            y_min = max(0, fake_y - 30)
            y_max = fake_y
        elif fake_x < fake_y:
            x_min = max(0, fake_x - radius_x)
            x_max = fake_x
            y_min = max(0, fake_y - radius_y)
            y_max = fake_y
        elif fake_x > fake_y:
            x_min = fake_x
            x_max = min(255, fake_x + radius_x)
            y_min = fake_y
            y_max = min(255, fake_y + radius_y)
        else:
            x_min = max(0, fake_x - radius_x)
            x_max = min(255, fake_x + radius_x)
            y_min = max(0, fake_y - radius_y)
            y_max = min(255, fake_y + radius_y)

        if rules.get("x_less"):
            x_max = min(x_max, fake_x)
        elif rules.get("x_less") is not None and not rules.get("x_less"):
            x_min = max(x_min, fake_x)

        if rules.get("y_less"):
            y_max = min(y_max, fake_y)
        elif rules.get("y_less") is not None and not rules.get("y_less"):
            y_min = max(y_min, fake_y)

        x_min = max(0, x_min)
        x_max = max(x_min + 10, x_max)
        y_min = max(0, y_min)
        y_max = max(y_min + 10, y_max)

        return {
            "center_x": int(adjusted_x),
            "center_y": int(adjusted_y),
            "x_min": int(x_min),
            "x_max": int(x_max),
            "y_min": int(y_min),
            "y_max": int(y_max),
            "radius_x": int(radius_x),
            "radius_y": int(radius_y),
            "map_name": map_name,
        }

    def record_feedback(self, fake_x, fake_y, real_x, real_y, map_name=""):
        offset_x = real_x - fake_x
        offset_y = real_y - fake_y

        if map_name not in self.learning_data:
            self.learning_data[map_name] = {
                "count": 0,
                "sum_offset_x": 0,
                "sum_offset_y": 0,
                "sum_sq_offset_x": 0,
                "sum_sq_offset_y": 0,
                "avg_offset_x": 0,
                "avg_offset_y": 0,
                "std_dev_x": 25,
                "std_dev_y": 25,
            }

        stats = self.learning_data[map_name]
        stats["count"] += 1
        stats["sum_offset_x"] += offset_x
        stats["sum_offset_y"] += offset_y
        stats["sum_sq_offset_x"] += offset_x ** 2
        stats["sum_sq_offset_y"] += offset_y ** 2

        n = stats["count"]
        stats["avg_offset_x"] = stats["sum_offset_x"] / n
        stats["avg_offset_y"] = stats["sum_offset_y"] / n
        
        var_x = (stats["sum_sq_offset_x"] / n) - (stats["avg_offset_x"] ** 2)
        var_y = (stats["sum_sq_offset_y"] / n) - (stats["avg_offset_y"] ** 2)
        stats["std_dev_x"] = max(5, float(np.sqrt(max(0, var_x))))
        stats["std_dev_y"] = max(5, float(np.sqrt(max(0, var_y))))

        self._save_learning_data()
        return stats

    def get_learning_stats(self, map_name=""):
        if map_name and map_name in self.learning_data:
            return self.learning_data[map_name]
        total_count = sum(stats["count"] for stats in self.learning_data.values())
        return {"total_samples": total_count, "maps": list(self.learning_data.keys())}


class PredictionOverlay:
    def __init__(self):
        self.running = False
        self.root = None
        self.canvas = None
        self.prediction_data = None
        self.thread = None
        self.update_event = threading.Event()
        self.map_image = None
        self.map_photo = None
        self.force_refresh = False

    def draw_prediction(self, prediction):
        self.prediction_data = prediction
        if not self.root:
            self.start()
        self.update_event.set()

    def set_map_image(self, image_path):
        if os.path.exists(image_path):
            self.map_image = image_path
            self.force_refresh = True
            if self.root:
                self.update_event.set()

    def clear_prediction(self):
        self.prediction_data = None
        self.force_refresh = True
        if self.root:
            self.update_event.set()

    def _init_overlay(self):
        import tkinter as tk
        from PIL import Image, ImageTk
        
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        transparent_color = "#00ff00"
        self.root.config(bg=transparent_color)
        self.root.wm_attributes('-transparentcolor', transparent_color)
        
        self.canvas = tk.Canvas(
            self.root,
            width=256,
            height=256,
            bg=transparent_color,
            highlightthickness=0
        )
        self.canvas.pack()
        
        self.root.geometry("256x256+0+0")
        self.root.update_idletasks()

    def start(self):
        self.running = True
        self.force_refresh = True
        if not self.thread:
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        self.update_event.set()
        if self.root:
            try:
                self.root.destroy()
            except:
                pass
            self.root = None
        self.thread = None

    def _run_loop(self):
        import tkinter as tk
        from PIL import Image, ImageTk
        
        self._init_overlay()
        
        while self.running:
            try:
                if self.prediction_data or self.force_refresh:
                    self.canvas.delete("all")
                    
                    if self.map_image and os.path.exists(self.map_image):
                        try:
                            img = Image.open(self.map_image)
                            img = img.resize((256, 256), Image.LANCZOS)
                            self.map_photo = ImageTk.PhotoImage(img)
                            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.map_photo)
                        except:
                            pass
                    
                    if self.prediction_data:
                        pred_type = self.prediction_data.get("type", "ghost")
                        
                        center_x = self.prediction_data["center_x"]
                        center_y = self.prediction_data["center_y"]
                        dot_x = center_x
                        dot_y = 255 - center_y
                        
                        if pred_type == "ghost":
                            x_min = self.prediction_data["x_min"]
                            x_max = self.prediction_data["x_max"]
                            y_min = self.prediction_data["y_min"]
                            y_max = self.prediction_data["y_max"]
                            
                            rect_x1 = x_min
                            rect_y1 = 255 - y_max
                            rect_x2 = x_max
                            rect_y2 = 255 - y_min
                            
                            self.canvas.create_rectangle(
                                rect_x1, rect_y1, rect_x2, rect_y2,
                                outline="red",
                                width=3,
                            )
                            
                            self.canvas.create_oval(
                                dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4,
                                fill="blue",
                                outline="white",
                                width=2
                            )
                        else:
                            self.canvas.create_oval(
                                dot_x - 6, dot_y - 6, dot_x + 6, dot_y + 6,
                                fill="#00ff00",
                                outline="white",
                                width=3
                            )
                        
                        self.prediction_data = None
                    
                    self.force_refresh = False
                    self.root.update_idletasks()
                
                self.root.update()
                self.update_event.wait(0.5)
                self.update_event.clear()
            except Exception as e:
                logger.error(f"Overlay error: {e}")
                break


MAP_IMAGE_URLS = {
    "建邺城": "http://img763.ph.126.net/OtaYkZm-hR5BT1-0b0TEkA==/4829266175424755617.jpg",
    "江南野外": "http://img.ph.126.net/8pjc6914DY7uTD8hkX3DyA==/3360811221926146626.jpg",
    "长安城": "http://img306.ph.126.net/lI_z4hwg_pPdxwLVCVZNMA==/3867466180004575695.jpg",
    "傲来国": "http://img.ph.126.net/wFATeMoaBIXW5qRjDNz2ig==/3292131327609226971.jpg",
    "长寿村": "http://img313.ph.126.net/aBzkScLnRX_iVmoujD5Ikw==/3670715171284119471.jpg",
    "五庄观": "http://img314.ph.126.net/Ic7vvfoOM2Ih5CiTxdN16g==/3873095679538787736.jpg",
    "普陀山": "http://img305.ph.126.net/aibdGVum5l8Jvtm7-VBgZw==/3756283564203865890.jpg",
    "大唐境外": "http://img.ph.126.net/jEQGL6PdbEoznnWQePO4yQ==/948852146492053545.jpg",
    "女儿村": "http://img314.ph.126.net/yE_DOHS2q_kUOhUg9yZ0-Q==/3871125354701813753.jpg",
    "北俱芦洲": "http://img.ph.126.net/28nSh2HmJEdipix7_hl86Q==/3238088132080800285.jpg",
    "麒麟山": "http://img.ph.126.net/cQMK5YGm2m_6BGFpwdK0SA==/3205718509758017633.jpg",
}

def get_map_image_path(map_name):
    maps_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "maps")
    os.makedirs(maps_dir, exist_ok=True)
    return os.path.join(maps_dir, f"{map_name}.jpg")

def download_map_image(map_name):
    save_path = get_map_image_path(map_name)
    if os.path.exists(save_path) and os.path.getsize(save_path) > 10000:
        return save_path
    return None

class GhostHunterPage(ft.Column):
    def __init__(self, data_manager, page):
        super().__init__()
        self.data_manager = data_manager
        self._page = page
        
        self.expand = True
        self.spacing = 15
        
        self.ocr = CoordinateOCR()
        self.predictor = GhostCoordinatePredictor()
        self.overlay = PredictionOverlay()
        
        self.is_running = False
        self.recognize_thread = None
        
        self.fake_x = 0
        self.fake_y = 0
        self.real_x = 0
        self.real_y = 0
        self.map_name = ""
        self.current_type = None
        
        self._build_ui()

    def _build_ui(self):
        self.title_text = ft.Text("👻 抓鬼辅助", size=24, weight=ft.FontWeight.BOLD)
        
        self.fake_x_field = ft.TextField(
            label="假坐标 X", 
            width=100,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_change=self._on_fake_coord_change
        )
        self.fake_y_field = ft.TextField(
            label="假坐标 Y", 
            width=100,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_change=self._on_fake_coord_change
        )
        
        self.map_dropdown = ft.Dropdown(
            label="地图",
            width=150,
            options=[
                ft.DropdownOption("未知"),
                ft.DropdownOption("建邺城"),
                ft.DropdownOption("东海湾"),
                ft.DropdownOption("江南野外"),
                ft.DropdownOption("长安城"),
                ft.DropdownOption("大唐国境"),
                ft.DropdownOption("大唐境外"),
                ft.DropdownOption("长寿村"),
                ft.DropdownOption("长寿郊外"),
                ft.DropdownOption("傲来国"),
                ft.DropdownOption("花果山"),
                ft.DropdownOption("月宫"),
                ft.DropdownOption("大唐官府"),
                ft.DropdownOption("方寸山"),
                ft.DropdownOption("化生寺"),
                ft.DropdownOption("女儿村"),
                ft.DropdownOption("魔王寨"),
                ft.DropdownOption("狮陀岭"),
                ft.DropdownOption("地府"),
                ft.DropdownOption("盘丝洞"),
                ft.DropdownOption("龙宫"),
                ft.DropdownOption("天宫"),
                ft.DropdownOption("五庄观"),
                ft.DropdownOption("普陀山"),
            ],
            value="未知",
            on_select=self._on_map_change
        )
        
        self.recognize_btn = ft.Button(
            "📷 识别坐标", 
            icon=ft.Icons.CAMERA_ALT,
            on_click=self._recognize_coordinates
        )
        
        self.toggle_btn = ft.ElevatedButton(
            "▶ 开启识别",
            icon=ft.Icons.PLAY_ARROW,
            color=ft.Colors.WHITE,
            bgcolor=ft.Colors.GREEN,
            on_click=self._toggle_recognition
        )

        self.lock_window_btn = ft.Button(
            "🔒 锁定梦幻西游",
            icon=ft.Icons.LOCK_OUTLINE,
            on_click=self._lock_game_window
        )

        self.select_map_panel_btn = ft.Button(
            "📍 框选地图面板",
            icon=ft.Icons.MAP,
            disabled=True,
            on_click=self._start_select_map_panel
        )

        self.select_ghost_task_btn = ft.Button(
            "👻 框选抓鬼任务",
            icon=ft.Icons.TASK,
            disabled=True,
            on_click=self._start_select_ghost_task
        )

        self.window_status_text = ft.Text(
            "未锁定 - 将截取全屏",
            size=13,
            color=ft.Colors.GREY,
        )

        self.unlock_btn = ft.IconButton(
            icon=ft.Icons.LOCK_OPEN,
            icon_size=20,
            tooltip="解除窗口锁定",
            visible=False,
            on_click=self._unlock_window
        )
        
        self.predict_result = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("预测结果", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Text("正在计算...", color=ft.Colors.GREY),
                ], spacing=10),
                padding=15,
            ),
        )
        
        self.map_image_container = ft.Container(
            content=ft.Text("选择地图后显示", color=ft.Colors.GREY),
            width=400,
            height=300,
            alignment=ft.Alignment(0, 0),
        )
        
        self.prediction_rect = ft.Container(
            width=0,
            height=0,
            left=0,
            top=0,
            border=ft.Border(
                top=ft.BorderSide(3, ft.Colors.RED),
                bottom=ft.BorderSide(3, ft.Colors.RED),
                left=ft.BorderSide(3, ft.Colors.RED),
                right=ft.BorderSide(3, ft.Colors.RED),
            ),
            bgcolor=ft.Colors.with_opacity(0.2, ft.Colors.YELLOW),
            visible=False,
        )
        
        self.map_stack = ft.Stack(
            [self.map_image_container, self.prediction_rect],
            width=400,
            height=300,
        )
        
        self.map_section = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("🗺️ 地图预测", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Row([self.map_stack], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([
                        ft.Button("选择地图图片", icon=ft.Icons.IMAGE, on_click=self._pick_map_image),
                        ft.Text("绿框为预测范围", size=12, color=ft.Colors.GREY),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                ], spacing=10),
                padding=15,
            ),
        )
        
        self.feedback_section = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("🎯 反馈学习", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Row([
                        ft.Text("真实坐标:", size=14),
                        ft.TextField(label="X", width=80, input_filter=ft.NumbersOnlyInputFilter(), 
                                    on_change=self._on_real_coord_change),
                        ft.TextField(label="Y", width=80, input_filter=ft.NumbersOnlyInputFilter(),
                                    on_change=self._on_real_coord_change),
                    ], spacing=10),
                    ft.Row([
                        ft.Button("提交反馈", icon=ft.Icons.SEND, on_click=self._submit_feedback),
                        ft.Button("快捷记录", icon=ft.Icons.SPEED, on_click=self._quick_feedback),
                    ], spacing=10),
                    ft.Text("反馈越多，预测越精准", size=12, color=ft.Colors.GREY),
                ], spacing=10),
                padding=15,
            ),
        )
        
        self.stats_section = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("📊 学习统计", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Text("暂无学习数据", color=ft.Colors.GREY),
                ], spacing=10),
                padding=15,
            ),
        )
        
        self.controls = [
            ft.Row([self.title_text], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Text("坐标输入", size=16, weight=ft.FontWeight.BOLD),
                        ft.Divider(),
                        ft.Row([
                            self.fake_x_field,
                            ft.Text(",", size=24, weight=ft.FontWeight.BOLD),
                            self.fake_y_field,
                            self.map_dropdown,
                            self.recognize_btn,
                            self.toggle_btn,
                        ], spacing=10, wrap=True, alignment=ft.MainAxisAlignment.CENTER),
                    ], spacing=10),
                    padding=15,
                ),
            ),
            
            self._build_window_lock_card(),
            self.map_section,
            self.predict_result,
            self.feedback_section,
            self.stats_section,
        ]
        
        self._update_stats()

    def _on_fake_coord_change(self, e):
        if self.current_type == "position":
            coords = None
            try:
                x = int(self.fake_x_field.value) if self.fake_x_field.value else 0
                y = int(self.fake_y_field.value) if self.fake_y_field.value else 0
                if x > 0 and y > 0:
                    coords = (x, y)
            except:
                pass
            map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
            self._update_position_display(coords, map_name)
        else:
            self._calculate_prediction()

    def _on_map_change(self, e):
        self.map_name = e.control.value
        self._load_map_image()
        map_name = e.control.value if e.control.value != "未知" else ""
        
        if map_name:
            map_path = get_map_image_path(map_name)
            self.overlay.set_map_image(map_path)
        
        if self.current_type == "position":
            coords = None
            try:
                x = int(self.fake_x_field.value) if self.fake_x_field.value else 0
                y = int(self.fake_y_field.value) if self.fake_y_field.value else 0
                if x > 0 and y > 0:
                    coords = (x, y)
            except:
                pass
            self._update_position_display(coords, map_name)
        else:
            self._calculate_prediction()

    def _on_real_coord_change(self, e):
        pass

    def _recognize_coordinates(self, e):
        try:
            result = self.ocr.recognize_coordinates()
            if result:
                coords = result.get("coords")
                map_name = result.get("map_name")
                recognize_type = result.get("type", "position")
                
                self.current_type = recognize_type
                
                if coords:
                    self.fake_x_field.value = str(coords[0])
                    self.fake_y_field.value = str(coords[1])
                    self.fake_x_field.update()
                    self.fake_y_field.update()
                
                if map_name:
                    self.map_dropdown.value = map_name
                    self.map_dropdown.update()
                    self._load_map_image()
                
                if recognize_type == "ghost":
                    self._calculate_prediction()
                    if coords and map_name:
                        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"👻 识别到抓鬼任务: {map_name} ({coords[0]}, {coords[1]})")))
                    elif coords:
                        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"👻 识别到抓鬼坐标: ({coords[0]}, {coords[1]})")))
                else:
                    self._update_position_display(coords, map_name)
                    if coords and map_name:
                        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"📍 当前位置: {map_name} ({coords[0]}, {coords[1]})")))
                    elif coords:
                        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"📍 当前坐标: ({coords[0]}, {coords[1]})")))
                    elif map_name:
                        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"📍 当前地图: {map_name}")))
            else:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("未识别到坐标，请尝试手动输入")))
        except Exception as ex:
            self._page.show_dialog(ft.SnackBar(content=ft.Text(f"识别失败: {str(ex)}")))

    def _toggle_recognition(self, e):
        if self.is_running:
            self._stop_recognition()
        else:
            self._start_recognition()

    def _start_recognition(self):
        self.is_running = True
        self._recognition_fail_count = 0
        self.toggle_btn.text = "⏹ 停止识别"
        self.toggle_btn.icon = ft.Icons.STOP
        self.toggle_btn.bgcolor = ft.Colors.RED
        self.toggle_btn.update()
        
        self.recognize_thread = threading.Thread(target=self._recognition_loop, daemon=True)
        self.recognize_thread.start()
        
        self.overlay.start()
        self._page.show_dialog(ft.SnackBar(content=ft.Text("开始自动识别，地图与预测范围将显示在屏幕左上角")))

    def _stop_recognition(self):
        self.is_running = False
        self.toggle_btn.text = "▶ 开启识别"
        self.toggle_btn.icon = ft.Icons.PLAY_ARROW
        self.toggle_btn.bgcolor = ft.Colors.GREEN
        self.toggle_btn.update()
        
        self.overlay.stop()
        self._page.show_dialog(ft.SnackBar(content=ft.Text("已停止识别")))

    def _recognition_loop(self):
        while self.is_running:
            try:
                result = self.ocr.recognize_coordinates()
                if result:
                    coords = result.get("coords")
                    map_name = result.get("map_name")
                    recognize_type = result.get("type", "position")
                    
                    self.current_type = recognize_type
                    self._recognition_fail_count = 0
                    
                    if coords:
                        self.fake_x_field.value = str(coords[0])
                        self.fake_y_field.value = str(coords[1])
                    
                    if map_name:
                        self.map_dropdown.value = map_name
                    
                    self._page.run_task(self._update_ui_after_recognition, recognize_type)
                    time.sleep(2)
                else:
                    self._recognition_fail_count += 1
                    
                    if self._recognition_fail_count >= 5:
                        logger.info(f"连续{self._recognition_fail_count}次识别失败，尝试重新获取窗口位置")
                        self._reacquire_window_position()
                        self._recognition_fail_count = 0
                        time.sleep(1)
                        continue
                    
                    self._page.run_task(self._update_map_only)
                    time.sleep(0.5)
            except:
                time.sleep(1)

    def _reacquire_window_position(self):
        """重新获取梦幻西游窗口位置并更新识别区域"""
        try:
            result = find_window_by_title("梦幻西游")
            if result:
                title, new_region = result
                old_region = self.ocr.custom_region
                
                if old_region and new_region != old_region:
                    self.ocr.set_window_region(new_region, title)
                    logger.info(f"窗口位置已更新: {old_region} -> {new_region}")
                    
                    self._load_region_config()
                    
                    self._page.run_task(lambda: self._page.show_dialog(
                        ft.SnackBar(content=ft.Text(f"📍 窗口位置已更新: {new_region}"))))
                else:
                    logger.debug("窗口位置未变化")
            else:
                logger.warning("重新获取窗口位置失败，未找到梦幻西游窗口")
        except Exception as e:
            logger.error(f"重新获取窗口位置异常: {e}")

    def _update_map_only(self):
        try:
            map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
            if map_name:
                map_path = get_map_image_path(map_name)
                self.overlay.set_map_image(map_path)
            self.overlay.clear_prediction()
        except RuntimeError:
            pass

    def _update_ui_after_recognition(self, recognize_type="position"):
        try:
            self.fake_x_field.update()
            self.fake_y_field.update()
            self.map_dropdown.update()
            self._load_map_image()
            
            if recognize_type == "ghost":
                self._calculate_prediction()
            else:
                coords = None
                if self.fake_x_field.value and self.fake_y_field.value:
                    coords = (int(self.fake_x_field.value), int(self.fake_y_field.value))
                map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
                self._update_position_display(coords, map_name)
        except RuntimeError:
            pass

    def _pick_map_image(self, e):
        def on_file_picked(result):
            if result and result.files and len(result.files) > 0:
                file_path = result.files[0].path
                if file_path and os.path.exists(file_path):
                    self.map_image_container.content = ft.Image(src=file_path, width=400, height=300)
                    try:
                        self.map_stack.update()
                    except RuntimeError:
                        pass
                    self._calculate_prediction()
        
        picker = ft.FilePicker(on_result=on_file_picked)
        self._page.overlay.append(picker)
        self._page.update()
        picker.pick_files(
            allowed_extensions=["jpg", "jpeg", "png", "bmp", "gif"],
            dialog_title="选择地图图片"
        )
    
    def _load_map_image(self):
        map_name = self.map_dropdown.value
        if map_name == "未知" or map_name not in MAP_IMAGE_URLS:
            self.map_image_container.content = ft.Text("选择地图后显示", color=ft.Colors.GREY)
            self.prediction_rect.visible = False
            try:
                self.map_stack.update()
            except RuntimeError:
                pass
            return
        
        map_path = get_map_image_path(map_name)
        if os.path.exists(map_path) and os.path.getsize(map_path) > 10000:
            self.map_image_container.content = ft.Image(src=map_path, width=400, height=300)
            try:
                self.map_stack.update()
            except RuntimeError:
                pass
        else:
            self.map_image_container.content = ft.Text("地图下载中...", color=ft.Colors.GREY)
            try:
                self.map_stack.update()
            except RuntimeError:
                pass
            threading.Thread(target=self._download_map_async, args=(map_name,), daemon=True).start()
    
    def _download_map_async(self, map_name):
        map_path = download_map_image(map_name)
        if map_path and os.path.exists(map_path):
            try:
                self.map_image_container.content = ft.Image(src=map_path, width=400, height=300)
                self.map_stack.update()
                self._calculate_prediction()
            except RuntimeError:
                pass
    
    def _update_map_prediction(self, prediction):
        if not isinstance(self.map_image_container.content, ft.Image):
            self.prediction_rect.visible = False
            try:
                self.map_stack.update()
            except RuntimeError:
                pass
            return
        
        img = self.map_image_container.content
        img_path = img.src
        
        try:
            pil_img = PILImage.open(img_path)
            actual_width, actual_height = pil_img.size
        except:
            actual_width, actual_height = 400, 300
        
        display_width = 400
        display_height = 300
        
        if actual_width > 0 and actual_height > 0:
            scale = min(display_width / actual_width, display_height / actual_height)
            img_display_width = actual_width * scale
            img_display_height = actual_height * scale
        else:
            img_display_width, img_display_height = display_width, display_height
        
        offset_x = (display_width - img_display_width) / 2
        offset_y = (display_height - img_display_height) / 2
        
        scale_x = img_display_width / 255.0
        scale_y = img_display_height / 255.0
        
        x_min = max(offset_x, offset_x + prediction["x_min"] * scale_x)
        x_max = min(offset_x + img_display_width, offset_x + prediction["x_max"] * scale_x)
        
        y_min_screen = offset_y + img_display_height - prediction["y_max"] * scale_y
        y_max_screen = offset_y + img_display_height - prediction["y_min"] * scale_y
        
        y_min_screen = max(offset_y, y_min_screen)
        y_max_screen = min(offset_y + img_display_height, y_max_screen)
        
        rect_width = max(10, x_max - x_min)
        rect_height = max(10, y_max_screen - y_min_screen)
        
        pred_type = prediction.get("type", "ghost")
        
        if pred_type == "ghost":
            self.prediction_rect.left = x_min
            self.prediction_rect.top = y_min_screen
            self.prediction_rect.width = rect_width
            self.prediction_rect.height = rect_height
            self.prediction_rect.border = ft.Border(
                top=ft.BorderSide(3, ft.Colors.RED),
                bottom=ft.BorderSide(3, ft.Colors.RED),
                left=ft.BorderSide(3, ft.Colors.RED),
                right=ft.BorderSide(3, ft.Colors.RED),
            )
            self.prediction_rect.bgcolor = ft.Colors.with_opacity(0.2, ft.Colors.YELLOW)
            self.prediction_rect.visible = True
        else:
            center_x = prediction["center_x"]
            center_y = prediction["center_y"]
            dot_x = offset_x + center_x * scale_x
            dot_y = offset_y + img_display_height - center_y * scale_y
            
            self.prediction_rect.left = max(offset_x, dot_x - 10)
            self.prediction_rect.top = max(offset_y, dot_y - 10)
            self.prediction_rect.width = 20
            self.prediction_rect.height = 20
            self.prediction_rect.border = ft.Border(
                top=ft.BorderSide(3, ft.Colors.GREEN),
                bottom=ft.BorderSide(3, ft.Colors.GREEN),
                left=ft.BorderSide(3, ft.Colors.GREEN),
                right=ft.BorderSide(3, ft.Colors.GREEN),
            )
            self.prediction_rect.bgcolor = ft.Colors.GREEN
            self.prediction_rect.visible = True
        
        try:
            self.prediction_rect.update()
        except RuntimeError:
            pass

    def _update_position_display(self, coords, map_name):
        if coords:
            x, y = coords
            self.predict_result.content.content = ft.Column([
                ft.Text("当前位置", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Row([
                    ft.Text("坐标:", size=14),
                    ft.Text(f"({x}, {y})", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                ], spacing=10),
                ft.Row([
                    ft.Text("地图:", size=14),
                    ft.Text(map_name or "未知", size=14, weight=ft.FontWeight.BOLD),
                ], spacing=10),
                ft.Text("📍 当前所在位置", size=14),
            ], spacing=10)
            
            try:
                self.predict_result.update()
            except RuntimeError:
                pass
            
            if map_name:
                map_path = get_map_image_path(map_name)
                self.overlay.set_map_image(map_path)
                position_info = self.predictor.get_position_info(x, y, map_name)
                self.overlay.draw_prediction(position_info)
                self._update_map_prediction(position_info)
        else:
            if map_name:
                self.predict_result.content.content = ft.Column([
                    ft.Text("当前位置", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Row([
                        ft.Text("地图:", size=14),
                        ft.Text(map_name, size=14, weight=ft.FontWeight.BOLD),
                    ], spacing=10),
                    ft.Text("📍 当前地图", size=14),
                ], spacing=10)
                
                try:
                    self.predict_result.update()
                except RuntimeError:
                    pass
                
                map_path = get_map_image_path(map_name)
                self.overlay.set_map_image(map_path)
                self.overlay.clear_prediction()

    def _calculate_prediction(self):
        try:
            x = int(self.fake_x_field.value) if self.fake_x_field.value else 0
            y = int(self.fake_y_field.value) if self.fake_y_field.value else 0
            map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
            
            if x == 0 and y == 0:
                self.predict_result.content.content = ft.Column([
                    ft.Text("预测结果", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Text("请输入坐标或点击识别", color=ft.Colors.GREY),
                ], spacing=10)
                try:
                    self.predict_result.update()
                except RuntimeError:
                    pass
                return
            
            prediction = self.predictor.predict_range(x, y, map_name)
            prediction["type"] = "ghost"
            
            self.predict_result.content.content = ft.Column([
                ft.Text("预测结果", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Row([
                    ft.Text("假坐标:", size=14),
                    ft.Text(f"({x}, {y})", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                ], spacing=10),
                ft.Row([
                    ft.Text("地图:", size=14),
                    ft.Text(map_name or "未知", size=14, weight=ft.FontWeight.BOLD),
                ], spacing=10),
                ft.Text("预测范围:", size=14),
                ft.Row([
                    ft.Text(f"X: {prediction['x_min']} - {prediction['x_max']}", size=14),
                    ft.Text(f"Y: {prediction['y_min']} - {prediction['y_max']}", size=14),
                ], spacing=20),
                ft.Text("搜索策略:", size=14),
                ft.Text(self._get_search_strategy(x, y, map_name), size=12, color=ft.Colors.GREEN),
            ], spacing=10)
            
            try:
                self.predict_result.update()
            except RuntimeError:
                pass
            
            if map_name:
                map_path = get_map_image_path(map_name)
                self.overlay.set_map_image(map_path)
            
            self.overlay.draw_prediction(prediction)
            self._update_map_prediction(prediction)
                
        except ValueError:
            pass

    def _get_search_strategy(self, x, y, map_name):
        strategies = []
        
        if map_name in ["五庄观", "普陀山"]:
            strategies.append(f"⚠️ {map_name}：真坐标必定小于假坐标")
        
        if x < 50:
            strategies.append("🔽 X坐标 < 50，向右下方向搜索")
        elif x > 150:
            strategies.append("🔼 X坐标 > 150，向右上方向搜索")
        
        if y < 50:
            strategies.append("⬇️ Y坐标 < 50，向下搜索")
        elif y > 150:
            strategies.append("⬆️ Y坐标 > 150，向上搜索")
        
        if 50 <= x <= 150 and 50 <= y <= 150:
            if x > y:
                strategies.append("📌 X > Y：优先向右下搜索")
            else:
                strategies.append("📌 X <= Y：优先向左上搜索")
        
        if not strategies:
            strategies.append("📍 在假坐标周围50范围内搜索")
        
        return "\n".join(strategies)

    def _quick_feedback(self, e):
        try:
            fake_x = int(self.fake_x_field.value) if self.fake_x_field.value else 0
            fake_y = int(self.fake_y_field.value) if self.fake_y_field.value else 0
            map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
            
            if fake_x == 0 or fake_y == 0:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请先输入或识别假坐标")))
                return
            
            real_fields = self.feedback_section.content.content.controls[2].controls
            real_x = int(real_fields[1].value) if real_fields[1].value else fake_x
            real_y = int(real_fields[2].value) if real_fields[2].value else fake_y
            
            stats = self.predictor.record_feedback(fake_x, fake_y, real_x, real_y, map_name)
            
            real_fields[1].value = ""
            real_fields[2].value = ""
            real_fields[1].update()
            real_fields[2].update()
            
            self._update_stats()
            self._calculate_prediction()
            
            self._page.show_dialog(ft.SnackBar(content=ft.Text(f"快捷反馈已记录！累计样本: {stats['count']}")))
            
        except ValueError:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("请输入有效的数字")))
    
    def _submit_feedback(self, e):
        try:
            fake_x = int(self.fake_x_field.value) if self.fake_x_field.value else 0
            fake_y = int(self.fake_y_field.value) if self.fake_y_field.value else 0
            map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
            
            real_fields = self.feedback_section.content.content.controls[2].controls
            real_x = int(real_fields[1].value) if real_fields[1].value else 0
            real_y = int(real_fields[2].value) if real_fields[2].value else 0
            
            if fake_x == 0 or fake_y == 0:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请先输入或识别假坐标")))
                return
            
            if real_x == 0 or real_y == 0:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请输入真实坐标")))
                return
            
            stats = self.predictor.record_feedback(fake_x, fake_y, real_x, real_y, map_name)
            
            real_fields[1].value = ""
            real_fields[2].value = ""
            real_fields[1].update()
            real_fields[2].update()
            
            self._update_stats()
            self._calculate_prediction()
            
            self._page.show_dialog(ft.SnackBar(content=ft.Text(f"反馈已记录！当前累计样本: {stats['count']}")))
            
        except ValueError:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("请输入有效的数字")))

    def _update_stats(self):
        stats = self.predictor.get_learning_stats()
        
        if stats["total_samples"] == 0:
            self.stats_section.content.content = ft.Column([
                ft.Text("📊 学习统计", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text("暂无学习数据", color=ft.Colors.GREY),
                ft.Text("提交反馈后，算法将逐渐学习提高精度", size=12, color=ft.Colors.GREY),
            ], spacing=10)
        else:
            maps_info = "\n".join([
                f"  {map_name}: {data['count']} 次"
                for map_name, data in self.predictor.learning_data.items()
            ])
            
            self.stats_section.content.content = ft.Column([
                ft.Text("📊 学习统计", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Row([
                    ft.Text("累计样本数:", size=14),
                    ft.Text(f"{stats['total_samples']}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                ], spacing=10),
                ft.Text("各地图数据:", size=14),
                ft.Text(maps_info, size=12),
                ft.Text("每次反馈都会帮助算法优化预测模型", size=12, color=ft.Colors.GREY),
            ], spacing=10)
        
        try:
            self.stats_section.update()
        except RuntimeError:
            pass

    def _build_window_lock_card(self):
        """构建窗口锁定卡片"""
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("🎯 窗口锁定", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Row([
                        self.lock_window_btn,
                        self.window_status_text,
                        self.unlock_btn,
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        self.select_map_panel_btn,
                        self.select_ghost_task_btn,
                    ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                ], spacing=10),
                padding=15,
            ),
        )

    def _lock_game_window(self, e):
        """锁定梦幻西游窗口并加载保存的区域配置"""
        try:
            result = find_window_by_title("梦幻西游")
            if result:
                title, region = result
                self.ocr.set_window_region(region, title)
                self.window_status_text.value = f"已锁定: {title}"
                self.window_status_text.color = ft.Colors.GREEN
                self.lock_window_btn.visible = False
                self.unlock_btn.visible = True
                self.select_map_panel_btn.disabled = False
                self.select_ghost_task_btn.disabled = False
                self._page.show_dialog(ft.SnackBar(content=ft.Text(f"已锁定窗口: {title}")))
                logger.info(f"窗口锁定成功: {title}, 区域: {region}")
                
                self._load_region_config()
                
            else:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("未找到梦幻西游窗口，请先启动游戏")))
                logger.warning("未找到匹配窗口")
        except Exception as ex:
            self._page.show_dialog(ft.SnackBar(content=ft.Text(f"锁定失败: {str(ex)}")))
            logger.error(f"窗口锁定异常: {ex}")
        self._page.update()

    def _unlock_window(self, e):
        """解除窗口锁定"""
        self.ocr.clear_window_region()
        self.window_status_text.value = "未锁定 - 将截取全屏"
        self.window_status_text.color = ft.Colors.GREY
        self.lock_window_btn.visible = True
        self.unlock_btn.visible = False
        self.select_map_panel_btn.disabled = True
        self.select_ghost_task_btn.disabled = True
        self._page.show_dialog(ft.SnackBar(content=ft.Text("OCR区域锁定已解除")))
        logger.info("窗口锁定已解除")
        self._page.update()

    def _start_select_map_panel(self, e):
        """开始框选地图面板区域"""
        self._start_region_selection("map_panel")

    def _start_select_ghost_task(self, e):
        """开始框选抓鬼任务区域"""
        self._start_region_selection("ghost_task")

    def _start_region_selection(self, region_type):
        """启动区域选择"""
        self._region_selection_type = region_type
        t = threading.Thread(target=self._run_region_selection, daemon=True)
        t.start()

    def _run_region_selection(self):
        """运行区域选择逻辑"""
        import tkinter as tk
        import ctypes
        
        user32 = ctypes.windll.user32
        
        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
        
        transparent_color = "#000001"
        root.config(bg=transparent_color)
        root.wm_attributes('-transparentcolor', transparent_color)
        
        canvas = tk.Canvas(root, bg=transparent_color, highlightthickness=0, cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)
        
        canvas.create_rectangle(
            0, 0, root.winfo_screenwidth(), root.winfo_screenheight(),
            fill="black", outline="", stipple="gray50"
        )
        
        canvas.create_text(root.winfo_screenwidth() // 2, root.winfo_screenheight() // 2,
                          text="按住鼠标左键拖动框选区域，按ESC取消",
                          fill="white", font=("Microsoft YaHei", 16),
                          anchor=tk.CENTER, tag="hint")
        
        start_x = start_y = end_x = end_y = 0
        rect_id = None
        fill_id = None
        selected_region = None
        
        def on_press(event):
            nonlocal start_x, start_y, rect_id, fill_id
            start_x, start_y = event.x, event.y
            canvas.delete("rect", "fill")
            
            fill_id = canvas.create_rectangle(start_x, start_y, start_x, start_y,
                                              fill="#00ffff", stipple="gray50",
                                              outline="", tag="fill")
            
            rect_id = canvas.create_rectangle(start_x, start_y, start_x, start_y, 
                                              outline="red", width=2, tag="rect")
        
        def on_drag(event):
            nonlocal end_x, end_y, rect_id, fill_id
            end_x, end_y = event.x, event.y
            
            canvas.delete("rect", "fill")
            
            fill_id = canvas.create_rectangle(start_x, start_y, end_x, end_y,
                                              fill="#00ffff", stipple="gray50",
                                              outline="", tag="fill")
            
            rect_id = canvas.create_rectangle(start_x, start_y, end_x, end_y, 
                                              outline="red", width=2, tag="rect")
        
        def on_release(event):
            nonlocal end_x, end_y, selected_region
            end_x, end_y = event.x, event.y
            
            region = (min(start_x, end_x), min(start_y, end_y), 
                     max(start_x, end_x), max(start_y, end_y))
            
            if region[2] - region[0] > 10 and region[3] - region[1] > 10:
                selected_region = region
                if self._region_selection_type == "map_panel":
                    self._save_map_panel_region(region)
                else:
                    self._save_ghost_task_region(region)
            
            root.quit()
        
        def on_esc(event):
            root.quit()
        
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind("<Escape>", on_esc)
        
        root.after(100, lambda: user32.SetForegroundWindow(root.winfo_id()))
        root.grab_set_global()
        root.focus_set()
        root.focus_force()
        
        root.mainloop()
        
        try:
            root.destroy()
        except:
            pass
        
        if selected_region:
            region_name = "地图面板" if self._region_selection_type == "map_panel" else "抓鬼任务"
            logger.info(f"区域选择完成: {region_name} - {selected_region}")

    def _save_map_panel_region(self, region):
        """保存地图面板区域配置（相对偏移量）"""
        config_dir = get_app_data_dir()
        config_path = os.path.join(config_dir, "region_config.json")
        
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                pass
        
        if self.ocr.custom_region:
            window_left, window_top, _, _ = self.ocr.custom_region
            offset_x = region[0] - window_left
            offset_y = region[1] - window_top
            width = region[2] - region[0]
            height = region[3] - region[1]
            
            config["map_panel_offset"] = (offset_x, offset_y, width, height)
            logger.info(f"地图面板相对偏移量已保存: ({offset_x}, {offset_y}, {width}, {height})")
        else:
            config["map_panel_region"] = region
        
        config["locked_window_region"] = self.ocr.custom_region
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass
        
        self.ocr.map_panel_region = region
        logger.info(f"地图面板区域已保存: {region}")

    def _save_ghost_task_region(self, region):
        """保存抓鬼任务区域配置（相对偏移量）"""
        config_dir = get_app_data_dir()
        config_path = os.path.join(config_dir, "region_config.json")
        
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                pass
        
        if self.ocr.custom_region:
            window_left, window_top, _, _ = self.ocr.custom_region
            offset_x = region[0] - window_left
            offset_y = region[1] - window_top
            width = region[2] - region[0]
            height = region[3] - region[1]
            
            config["ghost_task_offset"] = (offset_x, offset_y, width, height)
            logger.info(f"抓鬼任务相对偏移量已保存: ({offset_x}, {offset_y}, {width}, {height})")
        else:
            config["ghost_task_region"] = region
        
        config["locked_window_region"] = self.ocr.custom_region
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass
        
        self.ocr.ghost_task_region = region
        logger.info(f"抓鬼任务区域已保存: {region}")

    def did_mount(self):
        """页面挂载后自动锁定梦幻西游窗口并加载保存的区域配置"""
        try:
            result = find_window_by_title("梦幻西游")
            if result:
                title, region = result
                self.ocr.set_window_region(region, title)
                self.window_status_text.value = f"已锁定: {title}"
                self.window_status_text.color = ft.Colors.GREEN
                self.lock_window_btn.visible = False
                self.unlock_btn.visible = True
                self.select_map_panel_btn.disabled = False
                self.select_ghost_task_btn.disabled = False
                logger.info(f"自动锁定窗口成功: {title}, 区域: {region}")
                
                self._load_region_config()
                
                self._page.update()
        except Exception:
            pass

    def _load_region_config(self):
        """加载保存的区域配置并根据当前窗口位置计算实际区域"""
        config_dir = get_app_data_dir()
        config_path = os.path.join(config_dir, "region_config.json")
        
        if not os.path.exists(config_path):
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            window_left, window_top, _, _ = self.ocr.custom_region
            
            if "map_panel_offset" in config:
                offset_x, offset_y, width, height = config["map_panel_offset"]
                region = (
                    window_left + offset_x,
                    window_top + offset_y,
                    window_left + offset_x + width,
                    window_top + offset_y + height
                )
                self.ocr.map_panel_region = region
                logger.info(f"地图面板区域已从配置加载: {region}")
            elif "map_panel_region" in config:
                self.ocr.map_panel_region = config["map_panel_region"]
                logger.info(f"地图面板区域已从配置加载(绝对坐标): {self.ocr.map_panel_region}")
            
            if "ghost_task_offset" in config:
                offset_x, offset_y, width, height = config["ghost_task_offset"]
                region = (
                    window_left + offset_x,
                    window_top + offset_y,
                    window_left + offset_x + width,
                    window_top + offset_y + height
                )
                self.ocr.ghost_task_region = region
                logger.info(f"抓鬼任务区域已从配置加载: {region}")
            elif "ghost_task_region" in config:
                self.ocr.ghost_task_region = config["ghost_task_region"]
                logger.info(f"抓鬼任务区域已从配置加载(绝对坐标): {self.ocr.ghost_task_region}")
                
        except Exception as e:
            logger.error(f"加载区域配置失败: {e}")

    def will_unmount(self):
        self.cleanup()

    def cleanup(self):
        """清理页面资源：停止识别线程、关闭悬浮窗、释放截图资源"""
        if self.is_running:
            self.is_running = False
            if self.toggle_btn:
                self.toggle_btn.text = "▶ 开启识别"
                self.toggle_btn.icon = ft.Icons.PLAY_ARROW
                self.toggle_btn.bgcolor = ft.Colors.GREEN
        self.overlay.stop()
        try:
            self.ocr.screen_capture.close()
        except:
            pass
        logger.debug("GhostHunterPage资源已清理")