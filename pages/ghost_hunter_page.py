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
from utils.ocr_engine import get_ocr_engine, find_window_by_title, POINT

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


class CoordinateOCR:

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

        # 复用 utils.ocr_engine 的全局单例（跨页面共享，避免重复加载模型）
        engine = get_ocr_engine()
        if engine is not None:
            self.ocr = engine
            self._ocr_initialized = True
            logger.debug("复用共享 OCR 引擎")
        else:
            logger.error("OCR 引擎初始化失败（RapidOCR/EasyOCR 均不可用）")

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
        "龙宫", "天宫", "五庄观", "普陀山", "境外", "西梁女国", "无名城",
        "北俱芦洲", "麒麟山", "朱紫国", "宝象国", "碗子山", "墨家村",
        "女娲神迹", "小西天", "小雷音寺", "蓬莱仙岛", "柳林坡", "比丘国",
    ]

    SMALL_GHOST_PATTERNS = [
        r"钟[馗暌揆]", r"捉鬼", r"抓鬼", r"降伏.*鬼", r"缉拿.*鬼",
    ]
    BIG_GHOST_PATTERNS = [
        r"鬼王任务", r"挑战鬼王", r"降伏鬼王", r"鬼王",
    ]

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
        if not num_str.isdigit() or not 2 <= len(num_str) <= 6:
            return None
        splits = []
        for index in range(1, len(num_str)):
            if index > 3 or len(num_str) - index > 3:
                continue
            x, y = int(num_str[:index]), int(num_str[index:])
            if 0 <= x <= 999 and 0 <= y <= 999:
                # Prefer balanced digit groups, then the longer X group because
                # game maps (especially 大唐境外) commonly have a wider X axis.
                splits.append((abs(index - (len(num_str) - index)), -index, (x, y)))
        return min(splits)[2] if splits else None

    def _classify_ghost_task(self, text):
        """Return big/small/unknown, or None when text is not a ghost task."""
        compact = re.sub(r"\s+", "", text or "")
        if any(re.search(pattern, compact) for pattern in self.BIG_GHOST_PATTERNS):
            return "big"
        if any(re.search(pattern, compact) for pattern in self.SMALL_GHOST_PATTERNS):
            return "small"
        # OCR may preserve only a generic task phrase. Treat it as unknown instead
        # of guessing big/small, but still allow coordinate extraction.
        if "鬼" in compact and any(word in compact for word in ("任务", "坐标", "位置", "前往", "寻找")):
            return "unknown"
        return None

    def _extract_coordinate_candidates(self, text, map_name="", task_kind=None):
        """Extract and rank coordinates by their textual task context."""
        candidates = []
        normalized = (text or "").replace("（", "(").replace("）", ")")
        patterns = [
            (r"(?:坐标|位置|位于|前往|寻找)[^\d]{0,10}(\d{1,3})\s*[,，.。:：、]\s*(\d{1,3})", 12),
            (r"[\[(]\s*(\d{1,3})\s*[,，.。:：、\s]\s*(\d{1,3})\s*[\])]", 9),
            (r"(\d{1,3})\s*[,，.。:：、]\s*(\d{1,3})", 7),
            (r"(\d{1,3})\s+(\d{1,3})", 4),
        ]
        for pattern, base_score in patterns:
            for match in re.finditer(pattern, normalized):
                x, y = int(match.group(1)), int(match.group(2))
                if not (0 <= x <= 999 and 0 <= y <= 999):
                    continue
                context = normalized[max(0, match.start() - 24):match.end() + 24]
                score = base_score
                if map_name and map_name in context:
                    score += 5
                if self._classify_ghost_task(context) is not None:
                    score += 5
                if task_kind in ("big", "small") and self._classify_ghost_task(context) == task_kind:
                    score += 3
                if any(word in context for word in ("等级", "奖励", "次数", "时间", "分钟", "回合")):
                    score -= 6
                candidates.append((score, match.start(), (x, y)))

        # Some OCR engines merge bracketed coordinates, e.g. [7396].
        for match in re.finditer(r"[\[(](\d{3,6})[\])]", normalized):
            coords = self._split_coordinate(match.group(1))
            if coords:
                context = normalized[max(0, match.start() - 24):match.end() + 24]
                score = 6 + (5 if self._classify_ghost_task(context) is not None else 0)
                candidates.append((score, match.start(), coords))

        for match in re.finditer(r"(?:坐标|位置|位于|前往|寻找)[^\d]{0,8}(\d{3,6})(?!\d)", normalized):
            coords = self._split_coordinate(match.group(1))
            if coords:
                candidates.append((8, match.start(), coords))

        if not candidates:
            return None
        # Prefer the strongest contextual match; retain reading order for ties.
        candidates.sort(key=lambda item: (-item[0], item[1]))
        logger.debug(f"坐标候选: {candidates}")
        return candidates[0][2]

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
            map_text = ""
            task_text = ""
            
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
                
                map_text = " ".join(texts)

                if self.ghost_task_region:
                    img = self.capture_screen_region(self.ghost_task_region)
                    logger.debug(f"抓鬼任务区域截图: {self.ghost_task_region}")
                    
                    texts = ocr_image(img, "抓鬼任务")
                    if not texts:
                        processed_img = self.preprocess_image(img)
                        texts = ocr_image(processed_img, "抓鬼任务(预处理)")
                    
                    task_text = " ".join(texts)

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
                
                map_text = " ".join(texts)

            all_text = " ".join(part for part in (map_text, task_text) if part)
    
            if not all_text.strip():
                logger.debug("未识别到任何文字")
                return None
            
            corrected_text = self._correct_text(all_text)
            if corrected_text != all_text:
                logger.debug(f"文本修正: '{all_text}' -> '{corrected_text}'")
            all_text = corrected_text
    
            task_kind = self._classify_ghost_task(task_text)
            if task_kind is not None:
                map_name = self._extract_map_name(task_text) or self._extract_map_name(map_text)
                coords = self._extract_coordinate_candidates(task_text, map_name, task_kind)
                if coords:
                    result_data = {
                        "type": "ghost",
                        "ghost_size": task_kind,
                        "coords": coords,
                        "map_name": map_name,
                        "text": all_text,
                        "task_text": task_text,
                    }
                    logger.info(f"识别到{task_kind}抓鬼任务: {map_name} ({coords[0]}, {coords[1]})")
                    return result_data
                logger.warning(f"已识别抓鬼任务类型({task_kind})，但未找到可靠坐标: {task_text}")

            # No task was identified: parse only the map panel so task numbers
            # cannot be mistaken for the player's current position.
            map_name = self._extract_map_name(map_text)
            coords = self._extract_coordinate_candidates(map_text, map_name)
            if coords:
                return {
                    "type": "position",
                    "coords": coords,
                    "map_name": map_name,
                    "text": all_text,
                }
            
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
            (r'(大唐).*(境外)', '大唐境外'),
            (r'(大唐).*(国境)', '大唐国境'),
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
    BASE_RADIUS = 50
    MAX_SAMPLES_PER_MAP = 200

    def __init__(self):
        self.learning_data = {}
        self._load_learning_data()
        
        # Only cap maps whose coordinate extent is known. 大唐境外/境外 must not
        # use the old global 255 cap because its X coordinate can exceed 600.
        self.map_bounds = {
            "大唐境外": (0, 650, 0, 160),
            "境外": (0, 650, 0, 160),
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
        samples = self.learning_data.get(map_name, {}).get("samples", [])
        nearby = sorted(
            samples,
            key=lambda s: (s["fake_x"] - fake_x) ** 2 + (s["fake_y"] - fake_y) ** 2,
        )[:12]

        adjusted_x, adjusted_y = float(fake_x), float(fake_y)
        radius_x = radius_y = self.BASE_RADIUS
        confidence = "规则预测"
        if len(nearby) >= 3:
            distances = np.array([
                max(1.0, np.hypot(s["fake_x"] - fake_x, s["fake_y"] - fake_y))
                for s in nearby
            ])
            weights = 1.0 / distances
            offsets_x = np.array([s["real_x"] - s["fake_x"] for s in nearby], dtype=float)
            offsets_y = np.array([s["real_y"] - s["fake_y"] for s in nearby], dtype=float)
            # Median clipping prevents one incorrect feedback sample dominating the model.
            med_x, med_y = np.median(offsets_x), np.median(offsets_y)
            offsets_x = np.clip(offsets_x, med_x - 50, med_x + 50)
            offsets_y = np.clip(offsets_y, med_y - 50, med_y + 50)
            learned_x = float(np.average(offsets_x, weights=weights))
            learned_y = float(np.average(offsets_y, weights=weights))
            trust = min(0.85, len(nearby) / 15.0)
            adjusted_x = fake_x + learned_x * trust
            adjusted_y = fake_y + learned_y * trust
            radius_x = max(12, min(50, int(np.percentile(np.abs(offsets_x - learned_x), 90) + 12)))
            radius_y = max(12, min(50, int(np.percentile(np.abs(offsets_y - learned_y), 90) + 12)))
            confidence = "学习预测" if len(nearby) >= 8 else "规则 + 少量样本"

        # Official rule is ±50. Apply the verified edge-direction rule to X/Y
        # independently; coordinates in 51..149 have no reliable direction rule.
        x_min, x_max = fake_x - self.BASE_RADIUS, fake_x + self.BASE_RADIUS
        y_min, y_max = fake_y - self.BASE_RADIUS, fake_y + self.BASE_RADIUS
        if fake_x <= 50:
            x_max = fake_x
        elif fake_x >= 150:
            x_min = fake_x
        if fake_y <= 50:
            y_max = fake_y
        elif fake_y >= 150:
            y_min = fake_y

        min_x, max_x, min_y, max_y = self.map_bounds.get(map_name, (0, None, 0, None))
        x_min, y_min = max(min_x, x_min), max(min_y, y_min)
        if max_x is not None:
            x_max = min(max_x, x_max)
        if max_y is not None:
            y_max = min(max_y, y_max)

        # Learned point is a search priority, never a reason to discard the
        # guaranteed rule range. Keep it inside the final rectangle.
        adjusted_x = min(max(adjusted_x, x_min), x_max)
        adjusted_y = min(max(adjusted_y, y_min), y_max)

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
            "confidence": confidence,
            "sample_count": len(samples),
            "coord_max_x": max_x or 255,
            "coord_max_y": max_y or 255,
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
        stats.setdefault("samples", []).append({
            "fake_x": fake_x,
            "fake_y": fake_y,
            "real_x": real_x,
            "real_y": real_y,
        })
        stats["samples"] = stats["samples"][-self.MAX_SAMPLES_PER_MAP:]
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
    MAX_MAP_WIDTH = 460
    MAX_MAP_HEIGHT = 360
    HEADER_HEIGHT = 44

    def __init__(self):
        self.running = False
        self.root = None
        self.canvas = None
        self.prediction_data = None
        self.thread = None
        self.update_event = threading.Event()
        self.map_image = None
        self.force_refresh = False
        self._generation = 0
        self._lock = threading.RLock()

    def draw_prediction(self, prediction):
        with self._lock:
            self.prediction_data = dict(prediction)
            self.force_refresh = True
        self.start()
        self.update_event.set()

    def set_map_image(self, image_path):
        if os.path.exists(image_path):
            with self._lock:
                self.map_image = image_path
                self.force_refresh = True
            self.update_event.set()

    def clear_prediction(self):
        with self._lock:
            self.prediction_data = None
            self.force_refresh = True
        self.update_event.set()

    def _make_window_no_activate(self, root):
        """Keep the Windows overlay visible without taking focus from the game."""
        if sys.platform != "win32" or not root:
            return
        try:
            hwnd = root.winfo_id()
            user32 = ctypes.windll.user32
            gwl_exstyle = -20
            ws_ex_transparent = 0x00000020
            ws_ex_toolwindow = 0x00000080
            ws_ex_noactivate = 0x08000000
            style = user32.GetWindowLongW(hwnd, gwl_exstyle)
            user32.SetWindowLongW(
                hwnd,
                gwl_exstyle,
                style | ws_ex_transparent | ws_ex_toolwindow | ws_ex_noactivate,
            )
            hwnd_topmost = -1
            swp_nomove = 0x0002
            swp_nosize = 0x0001
            swp_noactivate = 0x0010
            user32.SetWindowPos(
                hwnd, hwnd_topmost, 0, 0, 0, 0,
                swp_nomove | swp_nosize | swp_noactivate,
            )
        except Exception as exc:
            logger.warning(f"设置无焦点悬浮窗失败，将继续使用普通置顶窗口: {exc}")

    def start(self):
        with self._lock:
            if self.running and self.thread and self.thread.is_alive():
                return
            self.running = True
            self.force_refresh = True
            self._generation += 1
            generation = self._generation
            self.thread = threading.Thread(
                target=self._run_loop,
                args=(generation,),
                daemon=True,
                name="prediction-overlay",
            )
            self.thread.start()

    def stop(self, timeout=3.0):
        with self._lock:
            self.running = False
            self._generation += 1
            thread = self.thread
        self.update_event.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("悬浮窗线程未在 %.1f 秒内结束", timeout)

    def _run_loop(self, generation):
        while self.running and generation == self._generation:
            try:
                self._run_window(generation)
            except Exception as exc:
                logger.exception(f"悬浮窗异常，将自动重建: {exc}")
            if self.running and generation == self._generation:
                time.sleep(1)
        with self._lock:
            if generation + 1 >= self._generation:
                self.root = None
                self.canvas = None
                self.thread = None

    def _run_window(self, generation):
        import tkinter as tk
        from PIL import Image, ImageTk

        transparent_color = "#00ff00"
        root = tk.Tk()
        root.title("")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.config(bg=transparent_color)
        root.wm_attributes("-transparentcolor", transparent_color)
        canvas = tk.Canvas(root, width=320, height=240, bg=transparent_color, highlightthickness=0)
        canvas.pack()
        root.geometry("320x240+20+80")
        root.update_idletasks()
        self._make_window_no_activate(root)
        with self._lock:
            self.root, self.canvas = root, canvas

        map_photo = None
        try:
            while self.running and generation == self._generation:
                if self.force_refresh:
                    map_photo = self._render(canvas, root, tk, Image, ImageTk)
                root.update_idletasks()
                root.update()
                self.update_event.wait(0.25)
                self.update_event.clear()
        finally:
            try:
                canvas.delete("all")
                map_photo = None
                root.update_idletasks()
                root.destroy()
            except Exception:
                pass

    def _render(self, canvas, root, tk, Image, ImageTk):
        with self._lock:
            prediction = dict(self.prediction_data) if self.prediction_data else None
            map_image = self.map_image
            self.force_refresh = False
        canvas.delete("all")
        if not map_image or not os.path.exists(map_image):
            return None

        with Image.open(map_image) as source:
            original_width, original_height = source.size
            scale = min(self.MAX_MAP_WIDTH / original_width, self.MAX_MAP_HEIGHT / original_height)
            draw_width = max(1, int(original_width * scale))
            draw_height = max(1, int(original_height * scale))
            resized = source.convert("RGB").resize((draw_width, draw_height), Image.LANCZOS)
        map_photo = ImageTk.PhotoImage(resized)
        total_height = self.HEADER_HEIGHT + draw_height
        canvas.config(width=draw_width, height=total_height)
        root.geometry(f"{draw_width}x{total_height}+20+80")
        canvas.create_rectangle(0, 0, draw_width, self.HEADER_HEIGHT, fill="#172033", outline="")
        canvas.create_image(0, self.HEADER_HEIGHT, anchor=tk.NW, image=map_photo)

        if not prediction:
            canvas.create_text(12, 22, text="等待坐标识别…", fill="white", anchor=tk.W, font=("Microsoft YaHei", 11, "bold"))
            return map_photo

        map_name = prediction.get("map_name") or "未知地图"
        ghost_label = {"big": "大鬼", "small": "小鬼", "unknown": "抓鬼"}.get(prediction.get("ghost_size"), "定位")
        confidence = prediction.get("confidence", "当前位置")
        sample_count = prediction.get("sample_count", 0)
        canvas.create_text(12, 14, text=f"{map_name} · {ghost_label}", fill="white", anchor=tk.W, font=("Microsoft YaHei", 11, "bold"))
        canvas.create_text(12, 33, text=f"{confidence} · 样本 {sample_count}", fill="#b9c7e6", anchor=tk.W, font=("Microsoft YaHei", 9))

        def map_point(game_x, game_y):
            calibrated = _game_to_map_pixel(map_name, game_x, game_y, map_image)
            if calibrated:
                return calibrated[0] * draw_width / calibrated[2], self.HEADER_HEIGHT + calibrated[1] * draw_height / calibrated[3]
            max_x = max(1, prediction.get("coord_max_x", 255))
            max_y = max(1, prediction.get("coord_max_y", 255))
            return game_x * draw_width / max_x, self.HEADER_HEIGHT + draw_height - game_y * draw_height / max_y

        dot_x, dot_y = map_point(prediction["center_x"], prediction["center_y"])
        if prediction.get("type", "ghost") == "ghost":
            corners = [
                map_point(gx, gy)
                for gx, gy in (
                    (prediction["x_min"], prediction["y_min"]),
                    (prediction["x_min"], prediction["y_max"]),
                    (prediction["x_max"], prediction["y_min"]),
                    (prediction["x_max"], prediction["y_max"]),
                )
            ]
            xs, ys = [p[0] for p in corners], [p[1] for p in corners]
            canvas.create_rectangle(min(xs), min(ys), max(xs), max(ys), outline="#ff3b30", width=4)
            canvas.create_oval(dot_x - 6, dot_y - 6, dot_x + 6, dot_y + 6, fill="#2196f3", outline="white", width=2)
        else:
            canvas.create_oval(dot_x - 7, dot_y - 7, dot_x + 7, dot_y + 7, fill="#00d26a", outline="white", width=3)

        return map_photo


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
    manifest = _load_captured_map_manifest()
    captured = manifest.get(map_name, {})
    captured_path = captured.get("path")
    if captured.get("status") == "approved" and captured_path and os.path.exists(captured_path):
        return captured_path
    previous_path = captured.get("previous_approved_path")
    if previous_path and os.path.exists(previous_path):
        return previous_path
    maps_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "maps")
    os.makedirs(maps_dir, exist_ok=True)
    return os.path.join(maps_dir, f"{map_name}.jpg")

def _captured_map_storage():
    storage_dir = os.path.join(get_app_data_dir(), "captured_maps")
    os.makedirs(storage_dir, exist_ok=True)
    return storage_dir, os.path.join(storage_dir, "manifest.json")

def _load_captured_map_manifest():
    _, manifest_path = _captured_map_storage()
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f"读取采集地图清单失败: {exc}")
        return {}

def _save_captured_map_manifest(manifest):
    _, manifest_path = _captured_map_storage()
    temp_path = manifest_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, manifest_path)

def _register_captured_map(map_name, image_path, region, image_size):
    manifest = _load_captured_map_manifest()
    previous = manifest.get(map_name, {})
    previous_approved_path = previous.get("previous_approved_path")
    previous_approved_calibration = previous.get("previous_approved_calibration")
    if previous.get("status") == "approved" and os.path.exists(previous.get("path", "")):
        previous_approved_path = previous["path"]
        previous_approved_calibration = previous.get("calibration")
    manifest[map_name] = {
        "path": os.path.abspath(image_path),
        "status": "pending",
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "region": list(region),
        "width": image_size[0],
        "height": image_size[1],
    }
    if previous_approved_path:
        manifest[map_name]["previous_approved_path"] = previous_approved_path
    if previous_approved_calibration:
        manifest[map_name]["previous_approved_calibration"] = previous_approved_calibration
    _save_captured_map_manifest(manifest)

def _set_captured_map_status(map_name, status):
    manifest = _load_captured_map_manifest()
    if map_name in manifest:
        manifest[map_name]["status"] = status
        manifest[map_name]["reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if status == "approved":
            manifest[map_name].pop("previous_approved_path", None)
            manifest[map_name].pop("previous_approved_calibration", None)
        _save_captured_map_manifest(manifest)

def _fit_map_calibration(points):
    if len(points) < 4:
        return None, "至少需要 4 个标定点；3 点会被精确拟合，无法判断点击误差"
    pixels = np.array([[p["pixel_x"], p["pixel_y"], 1.0] for p in points], dtype=float)
    games = np.array([[p["game_x"], p["game_y"]] for p in points], dtype=float)
    if np.linalg.matrix_rank(pixels) < 3:
        return None, "标定点接近共线，请选择分布在地图不同区域的点"
    coefficients, _, _, _ = np.linalg.lstsq(pixels, games, rcond=None)
    # Iteratively reweighted least squares (Huber-style) reduces the influence
    # of an occasional inaccurate click without silently discarding it.
    for _ in range(6):
        residuals = np.linalg.norm(pixels @ coefficients - games, axis=1)
        median = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - median)))
        threshold = max(1.5, 2.5 * 1.4826 * mad)
        weights = np.where(residuals <= threshold, 1.0, threshold / np.maximum(residuals, 1e-6))
        weighted_pixels = pixels * np.sqrt(weights)[:, None]
        weighted_games = games * np.sqrt(weights)[:, None]
        coefficients, _, _, _ = np.linalg.lstsq(weighted_pixels, weighted_games, rcond=None)
    predicted = pixels @ coefficients
    errors = np.linalg.norm(predicted - games, axis=1)
    linear = coefficients[:2, :]
    if abs(np.linalg.det(linear)) < 1e-8:
        return None, "标定矩阵不可逆，请重新选择标定点"
    inverse_linear = np.linalg.inv(linear)
    calibration = {
        "points": points,
        "pixel_to_game": coefficients.tolist(),
        "game_to_pixel_linear": inverse_linear.tolist(),
        "offset": coefficients[2, :].tolist(),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "max_error": float(np.max(errors)),
        "valid": bool(np.sqrt(np.mean(errors ** 2)) <= 5.0 and np.max(errors) <= 10.0),
    }
    if not calibration["valid"]:
        return calibration, f"标定误差过大：均方根 {calibration['rmse']:.2f}，最大 {calibration['max_error']:.2f}"
    return calibration, None

def _save_map_calibration(map_name, points):
    calibration, error = _fit_map_calibration(points)
    if calibration:
        manifest = _load_captured_map_manifest()
        if map_name in manifest:
            manifest[map_name]["calibration"] = calibration
            _save_captured_map_manifest(manifest)
    return calibration, error

def _game_to_map_pixel(map_name, game_x, game_y, image_path=None):
    item = _load_captured_map_manifest().get(map_name, {})
    active_path = item.get("path") if item.get("status") == "approved" else item.get("previous_approved_path")
    calibration = item.get("calibration", {}) if item.get("status") == "approved" else item.get("previous_approved_calibration", {})
    if image_path and active_path and os.path.normcase(os.path.abspath(image_path)) != os.path.normcase(os.path.abspath(active_path)):
        return None
    if not active_path or not os.path.exists(active_path) or not calibration.get("valid"):
        return None
    inverse = np.array(calibration["game_to_pixel_linear"], dtype=float)
    offset = np.array(calibration["offset"], dtype=float)
    pixel = (np.array([game_x, game_y], dtype=float) - offset) @ inverse
    return float(pixel[0]), float(pixel[1]), item.get("width", 1), item.get("height", 1)

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
        self.file_picker = ft.FilePicker()
        
        self.expand = True
        self.spacing = 15
        
        self.ocr = CoordinateOCR()
        self.predictor = GhostCoordinatePredictor()
        self.overlay = PredictionOverlay()
        
        self.is_running = False
        self.recognize_thread = None
        self._recognition_generation = 0
        
        self.fake_x = 0
        self.fake_y = 0
        self.real_x = 0
        self.real_y = 0
        self.map_name = ""
        self.current_type = None
        self.current_ghost_size = "unknown"
        self.workspace_tab_index = 0
        
        self._build_ui()

    def _build_ui(self):
        self.title_text = ft.Text("抓鬼辅助", size=26, weight=ft.FontWeight.BOLD)
        
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
        self.real_x_field = ft.TextField(
            label="真实 X", width=100, input_filter=ft.NumbersOnlyInputFilter(),
            on_change=self._on_real_coord_change,
        )
        self.real_y_field = ft.TextField(
            label="真实 Y", width=100, input_filter=ft.NumbersOnlyInputFilter(),
            on_change=self._on_real_coord_change,
        )
        
        self.map_dropdown = ft.Dropdown(
            label="地图",
            width=150,
            options=[ft.DropdownOption(name) for name in ["未知", *CoordinateOCR.MAP_NAMES]],
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
            disabled=True,
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
        self.header_window_status_text = ft.Text(
            "窗口未锁定", size=12, color=ft.Colors.ORANGE,
        )
        self.window_ready_text = ft.Text("1  锁定窗口", size=12)
        self.map_region_ready_text = ft.Text("2  框选地图面板", size=12)
        self.task_region_ready_text = ft.Text("3  框选抓鬼任务", size=12)

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
                    ft.Row([ft.Icon(ft.Icons.MAP, color=ft.Colors.PRIMARY), ft.Column([ft.Text("预测地图", size=18, weight=ft.FontWeight.BOLD), ft.Text("红框为建议搜索范围", size=11, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1)]),
                    ft.Divider(),
                    ft.Row([self.map_stack], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Text("地图图片优先使用审核通过的采集资源，内置地图作为保底。", size=11, color=ft.Colors.OUTLINE),
                ], spacing=10),
                padding=18,
            ),
        )
        self.map_management_section = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("地图资源", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("采集、标定并审核小地图；日常识别无需在这里操作", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Divider(),
                    ft.Row([
                        ft.Button("导入地图图片", icon=ft.Icons.IMAGE, on_click=self._pick_map_image),
                        ft.Button("采集当前地图", icon=ft.Icons.SCREENSHOT_MONITOR, on_click=self._start_map_capture),
                        ft.Button("审核采集结果", icon=ft.Icons.FACT_CHECK, on_click=self._show_map_capture_review),
                    ], spacing=10, wrap=True),
                    ft.Text("采集后至少使用 4 个分散点完成坐标标定，再通过审核启用。", size=11, color=ft.Colors.OUTLINE),
                ], spacing=10), padding=18,
            ),
        )
        
        self.feedback_section = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([ft.Icon(ft.Icons.NEAR_ME, color=ft.Colors.PRIMARY), ft.Column([ft.Text("真实坐标反馈", size=18, weight=ft.FontWeight.BOLD), ft.Text("找到目标后立即记录，不需要切换页面", size=11, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1)]),
                    ft.Divider(),
                    ft.Row([
                        self.real_x_field,
                        self.real_y_field,
                    ], spacing=10),
                    ft.Row([
                        ft.Button("提交反馈", icon=ft.Icons.SEND, on_click=self._submit_feedback),
                        ft.Button("快捷记录", icon=ft.Icons.SPEED, on_click=self._quick_feedback),
                    ], spacing=10),
                    ft.Text("到达目标后填写真实坐标并提交；快捷记录会在未填写时使用任务坐标。", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
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
        
        self.coordinate_input_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([ft.Icon(ft.Icons.CENTER_FOCUS_STRONG, color=ft.Colors.PRIMARY), ft.Column([ft.Text("任务识别", size=18, weight=ft.FontWeight.BOLD), ft.Text("自动识别优先，也可直接修正地图和任务坐标", size=11, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1)]),
                    ft.Divider(),
                    ft.Row([
                        self.fake_x_field,
                        self.fake_y_field,
                        self.map_dropdown,
                        self.recognize_btn,
                    ], spacing=10, wrap=True),
                ], spacing=10),
                padding=18,
            ),
        )
        self.recognition_view = ft.Column(
            [
                ft.Row([
                    ft.Column([self.coordinate_input_card, self.predict_result, self.feedback_section], spacing=12, expand=True),
                    ft.Container(content=self.map_section, width=470),
                ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.START),
            ],
            spacing=12, expand=True, scroll=ft.ScrollMode.AUTO,
        )
        self.map_view = ft.Column([self._build_window_lock_card(), self.map_management_section], spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
        self.learning_view = ft.Column(
            [self.stats_section],
            spacing=12, expand=True, scroll=ft.ScrollMode.AUTO,
        )
        self.workspace_tabs_row = ft.Row(spacing=8)
        self.workspace = ft.Stack(
            [self.recognition_view, self.map_view, self.learning_view],
            expand=True,
        )
        self._build_workspace_tabs()

        self.controls = [
            ft.Container(
                content=ft.Row([
                    ft.Column([self.title_text, ft.Text("实时识别任务坐标、显示搜索范围，并在同一页面完成真实坐标反馈", color=ft.Colors.ON_SURFACE_VARIANT)], spacing=2, expand=True),
                    self.header_window_status_text,
                    self.toggle_btn,
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=16, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=12,
            ),
            ft.Row([self.workspace_tabs_row, ft.Container(expand=True), ft.Text("建议先锁定游戏窗口和识别区域", size=12, color=ft.Colors.OUTLINE)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.workspace,
        ]
        
        self._update_stats()

    def _build_workspace_tabs(self):
        tabs = [
            ("开始前设置", ft.Icons.TUNE),
            ("实时辅助", ft.Icons.CENTER_FOCUS_STRONG),
            ("学习数据", ft.Icons.INSIGHTS),
        ]
        self.workspace_tabs_row.controls = [
            ft.Button(label, icon=icon, on_click=lambda e, index=i: self._switch_workspace_tab(index),
                      bgcolor=ft.Colors.PRIMARY_CONTAINER if i == self.workspace_tab_index else None)
            for i, (label, icon) in enumerate(tabs)
        ]
        views = [self.map_view, self.recognition_view, self.learning_view]
        for index, view in enumerate(views):
            view.visible = index == self.workspace_tab_index

    def _switch_workspace_tab(self, index):
        self.workspace_tab_index = index
        self._build_workspace_tabs()
        try:
            self.update()
        except RuntimeError:
            pass

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
                self.current_ghost_size = result.get("ghost_size", "unknown")
                
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
                    size_label = {"big": "大鬼（鬼王）", "small": "小鬼", "unknown": "抓鬼"}.get(
                        self.current_ghost_size, "抓鬼"
                    )
                    if coords and map_name:
                        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"👻 识别到{size_label}任务: {map_name} ({coords[0]}, {coords[1]})")))
                    elif coords:
                        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"👻 识别到{size_label}坐标: ({coords[0]}, {coords[1]})")))
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
        if not self._is_setup_ready():
            self.workspace_tab_index = 0
            self._build_workspace_tabs()
            try:
                self.update()
            except RuntimeError:
                pass
            self._page.show_dialog(ft.SnackBar(content=ft.Text("请先锁定游戏窗口并完成两个识别区域配置")))
            return
        if self.is_running:
            self._stop_recognition()
        else:
            self._start_recognition()

    def _start_recognition(self):
        if self.is_running:
            return
        self.is_running = True
        self._recognition_generation += 1
        generation = self._recognition_generation
        self._recognition_fail_count = 0
        self.toggle_btn.text = "⏹ 停止识别"
        self.toggle_btn.icon = ft.Icons.STOP
        self.toggle_btn.bgcolor = ft.Colors.RED
        self.toggle_btn.update()
        
        self.recognize_thread = threading.Thread(
            target=self._recognition_loop,
            args=(generation,),
            daemon=True,
            name="ghost-ocr-worker",
        )
        self.recognize_thread.start()
        
        self.overlay.start()
        self._page.show_dialog(ft.SnackBar(content=ft.Text("开始自动识别，地图与预测范围将显示在屏幕左上角")))

    def _stop_recognition(self):
        self.is_running = False
        self._recognition_generation += 1
        self.toggle_btn.text = "▶ 开启识别"
        self.toggle_btn.icon = ft.Icons.PLAY_ARROW
        self.toggle_btn.bgcolor = ft.Colors.GREEN
        self.toggle_btn.update()
        
        self.overlay.stop()
        self._page.show_dialog(ft.SnackBar(content=ft.Text("已停止识别")))

    def _recognition_loop(self, generation):
        logger.info(f"后台识别线程启动: generation={generation}")
        while self.is_running and generation == self._recognition_generation:
            try:
                result = self.ocr.recognize_coordinates()
                if result:
                    self._recognition_fail_count = 0
                    self._page.run_task(self._apply_recognition_result, result)
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
            except Exception as exc:
                logger.exception(f"后台识别异常，将在 1 秒后继续: {exc}")
                time.sleep(1)
        logger.info(f"后台识别线程结束: generation={generation}")

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
                    
                    self._page.run_task(self._show_snackbar_async, f"📍 窗口位置已更新: {new_region}")
                else:
                    logger.debug("窗口位置未变化")
            else:
                logger.warning("重新获取窗口位置失败，未找到梦幻西游窗口")
        except Exception as e:
            logger.error(f"重新获取窗口位置异常: {e}")

    async def _show_snackbar_async(self, message):
        self._page.show_dialog(ft.SnackBar(content=ft.Text(message)))

    async def _update_map_only(self):
        try:
            map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
            if map_name:
                map_path = get_map_image_path(map_name)
                self.overlay.set_map_image(map_path)
            self.overlay.clear_prediction()
        except RuntimeError:
            pass

    async def _apply_recognition_result(self, result):
        try:
            coords = result.get("coords")
            map_name = result.get("map_name")
            recognize_type = result.get("type", "position")
            self.current_type = recognize_type
            self.current_ghost_size = result.get("ghost_size", "unknown")
            if coords:
                self.fake_x_field.value = str(coords[0])
                self.fake_y_field.value = str(coords[1])
            if map_name:
                self.map_dropdown.value = map_name
            self.fake_x_field.update()
            self.fake_y_field.update()
            self.map_dropdown.update()
            self._load_map_image()
            
            if recognize_type == "ghost":
                self._calculate_prediction()
            else:
                self._update_position_display(coords, map_name)
        except RuntimeError:
            pass

    async def _pick_map_image(self, e):
        files = await self.file_picker.pick_files(
            allowed_extensions=["jpg", "jpeg", "png", "bmp", "gif"],
            dialog_title="选择地图图片",
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
        )
        if not files:
            return
        file_path = files[0].path
        if file_path and os.path.exists(file_path):
            self.map_image_container.content = ft.Image(src=file_path, width=400, height=300)
            try:
                self.map_stack.update()
            except RuntimeError:
                pass
            self._calculate_prediction()

    def _start_map_capture(self, e):
        map_name = self.map_dropdown.value
        if not map_name or map_name == "未知":
            self._page.show_dialog(ft.SnackBar(content=ft.Text("请先选择要采集的地图名称")))
            return
        self._page.show_dialog(ft.SnackBar(content=ft.Text("请拖动鼠标框选 Tab 小地图的纯地图区域，按 Esc 取消")))
        threading.Thread(target=self._run_map_capture_selection, args=(map_name,), daemon=True).start()

    def _run_map_capture_selection(self, map_name):
        import tkinter as tk

        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.35)
        root.configure(bg="black")
        canvas = tk.Canvas(root, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_text(
            root.winfo_screenwidth() // 2, 40,
            text=f"框选 {map_name} 的纯地图区域（不要包含窗口边框和坐标文字）",
            fill="white", font=("Microsoft YaHei", 16),
        )
        start = {"x": 0, "y": 0}
        selected = {"region": None}
        rectangle = {"id": None}

        def on_press(event):
            start["x"], start["y"] = event.x, event.y
            if rectangle["id"]:
                canvas.delete(rectangle["id"])
            rectangle["id"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#00ffff", width=3)

        def on_drag(event):
            if rectangle["id"]:
                canvas.coords(rectangle["id"], start["x"], start["y"], event.x, event.y)

        def on_release(event):
            left, right = sorted((start["x"], event.x))
            top, bottom = sorted((start["y"], event.y))
            if right - left >= 100 and bottom - top >= 80:
                selected["region"] = (left, top, right, bottom)
            root.quit()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind("<Escape>", lambda event: root.quit())
        root.mainloop()
        try:
            root.destroy()
        except Exception:
            pass

        region = selected["region"]
        if not region:
            return
        try:
            time.sleep(0.2)
            screenshot = self.ocr.capture_screen_region(region)
            screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
            image = PILImage.fromarray(screenshot)
            storage_dir, _ = _captured_map_storage()
            filename = f"{map_name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
            image_path = os.path.join(storage_dir, filename)
            image.save(image_path, "PNG")
            _register_captured_map(map_name, image_path, region, image.size)
            self._page.run_task(self._show_snackbar_async, f"{map_name} 已采集，审核通过后自动优先使用")
        except Exception as exc:
            logger.error(f"地图采集失败: {exc}")
            self._page.run_task(self._show_snackbar_async, f"地图采集失败: {exc}")

    def _show_map_capture_review(self, e=None):
        manifest = _load_captured_map_manifest()
        pending = [(name, item) for name, item in manifest.items() if item.get("status") == "pending"]
        if not pending:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("没有待审核的地图")))
            return

        review_list = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, height=460, width=620)

        def review(map_name, status):
            if status == "approved":
                item = _load_captured_map_manifest().get(map_name, {})
                calibration = item.get("calibration", {})
                if not calibration.get("valid"):
                    self._page.show_dialog(ft.SnackBar(content=ft.Text("请先完成有效的多点坐标标定，再审核通过")))
                    return
            _set_captured_map_status(map_name, status)
            self._page.pop_dialog()
            if status == "approved":
                if self.map_dropdown.value == map_name:
                    self._load_map_image()
                self._page.show_dialog(ft.SnackBar(content=ft.Text(f"{map_name} 已通过审核并优先使用")))
            else:
                self._page.show_dialog(ft.SnackBar(content=ft.Text(f"{map_name} 未通过审核，继续使用内置地图")))

        for map_name, item in pending:
            image_path = item.get("path", "")
            review_list.controls.append(ft.Card(content=ft.Container(content=ft.Column([
                ft.Row([
                    ft.Text(map_name, size=18, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{item.get('width', '?')}×{item.get('height', '?')}", color=ft.Colors.ON_SURFACE_VARIANT),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Image(src=image_path, width=560, height=300, fit=ft.BoxFit.CONTAIN),
                ft.Text(
                    self._calibration_status_text(item),
                    color=ft.Colors.GREEN if item.get("calibration", {}).get("valid") else ft.Colors.ORANGE,
                ),
                ft.Row([
                    ft.Button("标定坐标", icon=ft.Icons.CONTROL_POINT, on_click=lambda e, name=map_name: self._start_map_calibration(name)),
                    ft.Button("通过并启用", icon=ft.Icons.CHECK, on_click=lambda e, name=map_name: review(name, "approved")),
                    ft.Button("不通过", icon=ft.Icons.CLOSE, on_click=lambda e, name=map_name: review(name, "rejected")),
                ], alignment=ft.MainAxisAlignment.END),
            ], spacing=10), padding=12)))

        self._page.show_dialog(ft.AlertDialog(
            title=ft.Text("审核采集地图"),
            content=review_list,
            actions=[ft.TextButton("关闭", on_click=lambda e: self._page.pop_dialog())],
        ))

    def _calibration_status_text(self, item):
        calibration = item.get("calibration", {})
        if calibration.get("valid"):
            return (
                f"已标定 {len(calibration.get('points', []))} 点 · "
                f"RMSE {calibration.get('rmse', 0):.2f} · 最大误差 {calibration.get('max_error', 0):.2f}"
            )
        if calibration:
            return f"标定未通过 · RMSE {calibration.get('rmse', 0):.2f}"
        return "尚未标定：至少选择 4 个不共线的已知坐标点"

    def _start_map_calibration(self, map_name):
        self._page.pop_dialog()
        threading.Thread(target=self._run_map_calibration, args=(map_name,), daemon=True).start()

    def _run_map_calibration(self, map_name):
        import tkinter as tk
        from tkinter import messagebox, simpledialog
        from PIL import ImageTk

        item = _load_captured_map_manifest().get(map_name, {})
        image_path = item.get("path")
        if not image_path or not os.path.exists(image_path):
            return
        original = PILImage.open(image_path).convert("RGB")
        max_width, max_height = 1100, 720
        scale = min(max_width / original.width, max_height / original.height, 1.0)
        display = original.resize((int(original.width * scale), int(original.height * scale)), PILImage.LANCZOS)

        root = tk.Tk()
        root.title(f"标定地图坐标 - {map_name}")
        root.attributes("-topmost", True)
        info = tk.Label(root, text="点击地图上的已知位置并输入游戏坐标 X,Y；至少 4 点，建议 6 点以上且覆盖地图四周。", font=("Microsoft YaHei", 11))
        info.pack(padx=10, pady=8)
        canvas = tk.Canvas(root, width=display.width, height=display.height, highlightthickness=0)
        canvas.pack(padx=10)
        photo = ImageTk.PhotoImage(display)
        canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        points = list(item.get("calibration", {}).get("points", []))
        status = tk.StringVar(value="")

        def draw_points():
            canvas.delete("calibration_point")
            for index, point in enumerate(points, start=1):
                x, y = point["pixel_x"] * scale, point["pixel_y"] * scale
                canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#00ffff", outline="black", tags="calibration_point")
                canvas.create_text(x + 10, y - 10, text=f"{index}:({point['game_x']},{point['game_y']})", fill="red", anchor=tk.W, tags="calibration_point")
            calibration, error = _fit_map_calibration(points)
            if calibration:
                status.set(f"点数 {len(points)} · RMSE {calibration['rmse']:.2f} · 最大误差 {calibration['max_error']:.2f}" + (" · 可审核" if calibration["valid"] else " · 误差过大"))
            else:
                status.set(error or "")

        def add_point(event):
            value = simpledialog.askstring("输入游戏坐标", "请输入该位置的游戏坐标 X,Y，例如：120,85", parent=root)
            if not value:
                return
            match = re.fullmatch(r"\s*(\d{1,3})\s*[,，\s]\s*(\d{1,3})\s*", value)
            if not match:
                messagebox.showerror("格式错误", "请输入 X,Y，例如：120,85", parent=root)
                return
            points.append({
                "pixel_x": round(event.x / scale, 3),
                "pixel_y": round(event.y / scale, 3),
                "game_x": int(match.group(1)),
                "game_y": int(match.group(2)),
            })
            draw_points()

        def reset_points():
            points.clear()
            draw_points()

        def finish():
            calibration, error = _save_map_calibration(map_name, points)
            if error:
                messagebox.showerror("标定未通过", error, parent=root)
                return
            root.destroy()
            self._page.run_task(self._show_snackbar_async, f"{map_name} 标定完成，请重新打开审核窗口")

        canvas.bind("<Button-1>", add_point)
        controls = tk.Frame(root)
        controls.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(controls, textvariable=status, font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        tk.Button(controls, text="清空点位", command=reset_points).pack(side=tk.RIGHT, padx=5)
        tk.Button(controls, text="完成标定", command=finish).pack(side=tk.RIGHT, padx=5)
        draw_points()
        root.mainloop()
    
    def _load_map_image(self):
        map_name = self.map_dropdown.value
        if map_name == "未知":
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
            self._page.run_task(self._apply_downloaded_map, map_name, map_path)

    async def _apply_downloaded_map(self, map_name, map_path):
        if self.map_dropdown.value != map_name:
            return
        self.map_image_container.content = ft.Image(src=map_path, width=400, height=300)
        self.map_stack.update()
        self._calculate_prediction()
    
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
        
        map_name = prediction.get("map_name", "")
        calibrated_corners = [
            _game_to_map_pixel(map_name, gx, gy, img_path)
            for gx, gy in (
                (prediction["x_min"], prediction["y_min"]),
                (prediction["x_min"], prediction["y_max"]),
                (prediction["x_max"], prediction["y_min"]),
                (prediction["x_max"], prediction["y_max"]),
            )
        ]
        if all(calibrated_corners):
            image_scale = img_display_width / max(1, actual_width)
            xs = [offset_x + point[0] * image_scale for point in calibrated_corners]
            ys = [offset_y + point[1] * image_scale for point in calibrated_corners]
            x_min, x_max = min(xs), max(xs)
            y_min_screen, y_max_screen = min(ys), max(ys)
            scale_x = scale_y = image_scale
        else:
            scale_x = img_display_width / max(1, prediction.get("coord_max_x", 255))
            scale_y = img_display_height / max(1, prediction.get("coord_max_y", 255))
            x_min = offset_x + prediction["x_min"] * scale_x
            x_max = offset_x + prediction["x_max"] * scale_x
            y_min_screen = offset_y + img_display_height - prediction["y_max"] * scale_y
            y_max_screen = offset_y + img_display_height - prediction["y_min"] * scale_y

        x_min = max(offset_x, x_min)
        x_max = min(offset_x + img_display_width, x_max)
        
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
            calibrated_center = _game_to_map_pixel(map_name, center_x, center_y, img_path)
            if calibrated_center:
                image_scale = img_display_width / max(1, actual_width)
                dot_x = offset_x + calibrated_center[0] * image_scale
                dot_y = offset_y + calibrated_center[1] * image_scale
            else:
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
            prediction["ghost_size"] = self.current_ghost_size
            
            self.predict_result.content.content = ft.Column([
                ft.Text("预测结果", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text(
                    {"big": "大鬼（鬼王）", "small": "小鬼（钟馗捉鬼）", "unknown": "抓鬼任务"}.get(
                        self.current_ghost_size, "抓鬼任务"
                    ),
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.PRIMARY,
                ),
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
                ft.Text(
                    f"{prediction['confidence']} · 地图样本 {prediction['sample_count']} 条",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
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
        
        if x <= 50:
            strategies.append("X ≤ 50：只搜索假坐标左侧")
        elif x >= 150:
            strategies.append("X ≥ 150：只搜索假坐标右侧")
        if y <= 50:
            strategies.append("Y ≤ 50：只搜索假坐标下方")
        elif y >= 150:
            strategies.append("Y ≥ 150：只搜索假坐标上方")

        sample_count = len(self.predictor.learning_data.get(map_name, {}).get("samples", []))
        if sample_count >= 3:
            strategies.append(f"优先检查蓝色预测点附近（参考 {sample_count} 条反馈）")
        
        if not strategies:
            strategies.append("在假坐标横纵 ±50 的完整范围内搜索")
        
        return "\n".join(strategies)

    def _quick_feedback(self, e):
        try:
            fake_x = int(self.fake_x_field.value) if self.fake_x_field.value else 0
            fake_y = int(self.fake_y_field.value) if self.fake_y_field.value else 0
            map_name = self.map_dropdown.value if self.map_dropdown.value != "未知" else ""
            
            if fake_x == 0 or fake_y == 0:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请先输入或识别假坐标")))
                return
            
            real_x = int(self.real_x_field.value) if self.real_x_field.value else fake_x
            real_y = int(self.real_y_field.value) if self.real_y_field.value else fake_y
            
            stats = self.predictor.record_feedback(fake_x, fake_y, real_x, real_y, map_name)
            
            self.real_x_field.value = ""
            self.real_y_field.value = ""
            self.real_x_field.update()
            self.real_y_field.update()
            
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
            
            real_x = int(self.real_x_field.value) if self.real_x_field.value else 0
            real_y = int(self.real_y_field.value) if self.real_y_field.value else 0
            
            if fake_x == 0 or fake_y == 0:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请先输入或识别假坐标")))
                return
            
            if real_x == 0 or real_y == 0:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请输入真实坐标")))
                return
            
            stats = self.predictor.record_feedback(fake_x, fake_y, real_x, real_y, map_name)
            
            self.real_x_field.value = ""
            self.real_y_field.value = ""
            self.real_x_field.update()
            self.real_y_field.update()
            
            self._update_stats()
            self._calculate_prediction()
            
            self._page.show_dialog(ft.SnackBar(content=ft.Text(f"反馈已记录！当前累计样本: {stats['count']}")))
            
        except ValueError:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("请输入有效的数字")))

    def _update_stats(self):
        stats = self.predictor.get_learning_stats()
        
        if stats["total_samples"] == 0:
            self.stats_section.content.content = ft.Column([
                ft.Row([ft.Icon(ft.Icons.INSIGHTS, color=ft.Colors.PRIMARY), ft.Column([ft.Text("学习数据", size=18, weight=ft.FontWeight.BOLD), ft.Text("真实坐标反馈会按地图积累为本地样本", size=12, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1)]),
                ft.Divider(),
                ft.Container(content=ft.Column([ft.Icon(ft.Icons.DATASET_OUTLINED, size=48, color=ft.Colors.OUTLINE), ft.Text("暂无学习样本", weight=ft.FontWeight.BOLD), ft.Text("在“实时辅助”中提交一次真实坐标即可开始积累", size=12, color=ft.Colors.ON_SURFACE_VARIANT)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=32, alignment=ft.Alignment.CENTER),
            ], spacing=10)
        else:
            map_cards = [
                ft.Container(content=ft.Row([ft.Icon(ft.Icons.MAP_OUTLINED, color=ft.Colors.PRIMARY), ft.Text(map_name, expand=True), ft.Text(f"{data['count']} 条", weight=ft.FontWeight.BOLD)]), padding=12, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=10, width=260)
                for map_name, data in self.predictor.learning_data.items()
            ]
            self.stats_section.content.content = ft.Column([
                ft.Row([ft.Icon(ft.Icons.INSIGHTS, color=ft.Colors.PRIMARY), ft.Column([ft.Text("学习数据", size=18, weight=ft.FontWeight.BOLD), ft.Text("样本仅保存在本机，用于修正各地图预测", size=12, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1)]),
                ft.Divider(),
                ft.Container(content=ft.Row([ft.Text("累计有效样本", expand=True), ft.Text(str(stats["total_samples"]), size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY)]), padding=16, bgcolor=ft.Colors.PRIMARY_CONTAINER, border_radius=12),
                ft.Text("地图样本分布", weight=ft.FontWeight.BOLD),
                ft.Row(map_cards, spacing=10, wrap=True),
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
                    ft.Row([ft.Icon(ft.Icons.WINDOW, color=ft.Colors.PRIMARY), ft.Column([ft.Text("游戏窗口与识别区域", size=18, weight=ft.FontWeight.BOLD), ft.Text("锁定后只截取游戏窗口；继续框选任务栏和地图面板可提高识别稳定性", size=12, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1)]),
                    ft.Divider(),
                    ft.Row([
                        self._setup_step_chip(self.window_ready_text),
                        self._setup_step_chip(self.map_region_ready_text),
                        self._setup_step_chip(self.task_region_ready_text),
                    ], spacing=8),
                    ft.Row([
                        self.lock_window_btn,
                        self.window_status_text,
                        self.unlock_btn,
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        self.select_map_panel_btn,
                        self.select_ghost_task_btn,
                    ], spacing=10),
                    ft.Text("推荐顺序：锁定梦幻西游 → 框选地图面板 → 框选抓鬼任务。区域配置会自动保存。", size=11, color=ft.Colors.OUTLINE),
                ], spacing=10),
                padding=18,
            ),
        )

    def _setup_step_chip(self, text_control):
        return ft.Container(content=text_control, padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=18)

    def _is_setup_ready(self):
        return bool(self.ocr.custom_region and self.ocr.map_panel_region and self.ocr.ghost_task_region)

    def _refresh_setup_readiness(self):
        states = (
            (self.window_ready_text, bool(self.ocr.custom_region), "1  窗口已锁定", "1  锁定窗口"),
            (self.map_region_ready_text, bool(self.ocr.map_panel_region), "2  地图面板已配置", "2  框选地图面板"),
            (self.task_region_ready_text, bool(self.ocr.ghost_task_region), "3  抓鬼任务已配置", "3  框选抓鬼任务"),
        )
        for control, ready, ready_text, waiting_text in states:
            control.value = ready_text if ready else waiting_text
            control.color = ft.Colors.GREEN if ready else ft.Colors.ORANGE
        ready = self._is_setup_ready()
        self.toggle_btn.disabled = not ready
        self.header_window_status_text.value = "识别配置已就绪" if ready else ("游戏窗口已锁定，区域待配置" if self.ocr.custom_region else "窗口未锁定")
        self.header_window_status_text.color = ft.Colors.GREEN if ready else ft.Colors.ORANGE
        for control in [* [item[0] for item in states], self.toggle_btn, self.header_window_status_text]:
            try:
                control.update()
            except RuntimeError:
                pass

    async def _refresh_setup_readiness_async(self):
        self._refresh_setup_readiness()

    def _lock_game_window(self, e):
        """锁定梦幻西游窗口并加载保存的区域配置"""
        try:
            result = find_window_by_title("梦幻西游")
            if result:
                title, region = result
                self.ocr.set_window_region(region, title)
                self.window_status_text.value = f"已锁定: {title}"
                self.window_status_text.color = ft.Colors.GREEN
                self.header_window_status_text.value = "游戏窗口已锁定"
                self.header_window_status_text.color = ft.Colors.GREEN
                self.lock_window_btn.visible = False
                self.unlock_btn.visible = True
                self.select_map_panel_btn.disabled = False
                self.select_ghost_task_btn.disabled = False
                self._page.show_dialog(ft.SnackBar(content=ft.Text(f"已锁定窗口: {title}")))
                logger.info(f"窗口锁定成功: {title}, 区域: {region}")
                
                self._load_region_config()
                self._refresh_setup_readiness()
                
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
        self.header_window_status_text.value = "窗口未锁定"
        self.header_window_status_text.color = ft.Colors.ORANGE
        self.lock_window_btn.visible = True
        self.unlock_btn.visible = False
        self.select_map_panel_btn.disabled = True
        self.select_ghost_task_btn.disabled = True
        self._refresh_setup_readiness()
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
        try:
            self._page.run_task(self._refresh_setup_readiness_async)
        except Exception:
            pass

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
        try:
            self._page.run_task(self._refresh_setup_readiness_async)
        except Exception:
            pass

    def did_mount(self):
        """页面挂载后自动锁定梦幻西游窗口并加载保存的区域配置"""
        try:
            result = find_window_by_title("梦幻西游")
            if result:
                title, region = result
                self.ocr.set_window_region(region, title)
                self.window_status_text.value = f"已锁定: {title}"
                self.window_status_text.color = ft.Colors.GREEN
                self.header_window_status_text.value = "游戏窗口已锁定"
                self.header_window_status_text.color = ft.Colors.GREEN
                self.lock_window_btn.visible = False
                self.unlock_btn.visible = True
                self.select_map_panel_btn.disabled = False
                self.select_ghost_task_btn.disabled = False
                logger.info(f"自动锁定窗口成功: {title}, 区域: {region}")
                
                self._load_region_config()
                self._refresh_setup_readiness()
                if self._is_setup_ready():
                    self.workspace_tab_index = 1
                    self._build_workspace_tabs()
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
            self._refresh_setup_readiness()
        except Exception as e:
            logger.error(f"加载区域配置失败: {e}")

    def will_unmount(self):
        self.cleanup()

    def cleanup(self):
        """清理页面资源：停止识别线程、关闭悬浮窗、释放截图资源"""
        if self.is_running:
            self.is_running = False
            self._recognition_generation += 1
            if self.toggle_btn:
                self.toggle_btn.text = "▶ 开启识别"
                self.toggle_btn.icon = ft.Icons.PLAY_ARROW
                self.toggle_btn.bgcolor = ft.Colors.GREEN
        self.overlay.stop()
        recognition_thread = self.recognize_thread
        if recognition_thread and recognition_thread is not threading.current_thread():
            recognition_thread.join(timeout=3.0)
            if recognition_thread.is_alive():
                logger.warning("后台识别线程未在 3.0 秒内结束")
        try:
            self.ocr.screen_capture.close()
        except Exception as exc:
            logger.debug(f"关闭截图资源失败: {exc}")
        logger.debug("GhostHunterPage资源已清理")
