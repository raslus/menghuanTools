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
import urllib.request
import requests
from PIL import Image as PILImage
from platform_utils import get_app_data_dir

try:
    from paddleocr import PaddleOCR
    _paddleocr_available = True
except ImportError:
    _paddleocr_available = False


class CoordinateOCR:
    def __init__(self):
        self.screen_capture = mss.mss()
        self.monitor = self.screen_capture.monitors[1]
        self.ocr = None
        self._ocr_initialized = False

    def _init_ocr(self):
        if self._ocr_initialized or not _paddleocr_available:
            return
        try:
            self.ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            self._ocr_initialized = True
        except Exception:
            pass

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
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return img

    def get_screen_size(self):
        primary_monitor = self.screen_capture.monitors[1]
        return primary_monitor["width"], primary_monitor["height"]

    def recognize_coordinates(self, search_region=None):
        if not _paddleocr_available:
            return None
        
        self._init_ocr()
        if self.ocr is None:
            return None

        try:
            if search_region:
                img = self.capture_screen_region(search_region)
            else:
                screen_width, screen_height = self.get_screen_size()
                taskbar_height = 50
                taskbar_region = (0, screen_height - taskbar_height, screen_width, screen_height)
                img = self.capture_screen_region(taskbar_region)

            result = self.ocr.ocr(img, cls=True)
            
            if result and len(result) > 0:
                all_text = ""
                for line in result[0]:
                    if line and len(line) > 1:
                        all_text += line[1][0] + " "
                
                coords = self._parse_coordinates(all_text)
                if coords:
                    return coords

            full_screen_img = self.capture_screen_region()
            result_full = self.ocr.ocr(full_screen_img, cls=True)
            
            if result_full and len(result_full) > 0:
                all_text = ""
                for line in result_full[0]:
                    if line and len(line) > 1:
                        all_text += line[1][0] + " "
                
                return self._parse_coordinates(all_text)
            
            return None
            
        except Exception as e:
            return None

    def _parse_coordinates(self, text):
        pattern = r'(\d{1,3})\s*[,.，。、]\s*(\d{1,3})'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1)), int(match.group(2))
        
        pattern2 = r'(\d{1,3})\s+(\d{1,3})'
        match2 = re.search(pattern2, text)
        if match2:
            return int(match2.group(1)), int(match2.group(2))
        
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

    def draw_prediction(self, prediction):
        self.prediction_data = prediction
        if not self.root:
            self.start()
        self.update_event.set()

    def _init_overlay(self):
        import tkinter as tk
        
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        transparent_color = "#00ff00"
        self.root.config(bg=transparent_color)
        self.root.wm_attributes('-transparentcolor', transparent_color)
        
        self.canvas = tk.Canvas(
            self.root,
            width=500,
            height=300,
            bg=transparent_color,
            highlightthickness=0
        )
        self.canvas.pack()
        
        self.root.geometry("500x300+0+0")
        self.root.update_idletasks()

    def start(self):
        self.running = True
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
        
        self._init_overlay()
        
        while self.running:
            try:
                if self.prediction_data:
                    x_min, x_max = self.prediction_data["x_min"], self.prediction_data["x_max"]
                    y_min, y_max = self.prediction_data["y_min"], self.prediction_data["y_max"]
                    center_x = self.prediction_data["center_x"]
                    center_y = self.prediction_data["center_y"]
                    map_name = self.prediction_data.get("map_name", "")
                    
                    lines = [
                        f"预测范围",
                        f"假坐标: ({center_x}, {center_y})",
                        f"地图: {map_name or '未知'}",
                        f"X: {x_min}-{x_max}",
                        f"Y: {y_min}-{y_max}"
                    ]
                    
                    self.canvas.delete("all")
                    y_offset = 40
                    for line in lines:
                        self.canvas.create_text(
                            20, y_offset,
                            text=line,
                            font=("Microsoft YaHei", 32, "bold"),
                            fill="red",
                            anchor="w"
                        )
                        y_offset += 45
                    
                    self.root.update_idletasks()
                    self.prediction_data = None
                
                self.root.update()
                self.update_event.wait(0.5)
                self.update_event.clear()
            except Exception as e:
                print(f"Overlay error: {e}")
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
            
            self.map_section,
            self.predict_result,
            self.feedback_section,
            self.stats_section,
        ]
        
        self._update_stats()

    def _on_fake_coord_change(self, e):
        self._calculate_prediction()

    def _on_map_change(self, e):
        self.map_name = e.control.value
        self._load_map_image()
        self._calculate_prediction()

    def _on_real_coord_change(self, e):
        pass

    def _recognize_coordinates(self, e):
        try:
            result = self.ocr.recognize_coordinates()
            if result:
                self.fake_x_field.value = str(result[0])
                self.fake_y_field.value = str(result[1])
                self.fake_x_field.update()
                self.fake_y_field.update()
                self._calculate_prediction()
                self._page.show_dialog(ft.SnackBar(content=ft.Text(f"识别成功: ({result[0]}, {result[1]})")))
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
        self.toggle_btn.text = "⏹ 停止识别"
        self.toggle_btn.icon = ft.Icons.STOP
        self.toggle_btn.bgcolor = ft.Colors.RED
        self.toggle_btn.update()
        
        self.recognize_thread = threading.Thread(target=self._recognition_loop, daemon=True)
        self.recognize_thread.start()
        
        self.overlay.start()
        self._page.show_dialog(ft.SnackBar(content=ft.Text("开始自动识别，预测范围将显示在屏幕左上角")))

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
                    self.fake_x_field.value = str(result[0])
                    self.fake_y_field.value = str(result[1])
                    
                    self._page.run_task(self._update_ui_after_recognition)
                    time.sleep(2)
                else:
                    time.sleep(0.5)
            except:
                time.sleep(1)

    def _update_ui_after_recognition(self):
        try:
            self.fake_x_field.update()
            self.fake_y_field.update()
            self._calculate_prediction()
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
        
        self.prediction_rect.left = x_min
        self.prediction_rect.top = y_min_screen
        self.prediction_rect.width = rect_width
        self.prediction_rect.height = rect_height
        self.prediction_rect.visible = True
        
        try:
            self.prediction_rect.update()
        except RuntimeError:
            pass

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

    def did_mount(self):
        pass

    def will_unmount(self):
        self._stop_recognition()