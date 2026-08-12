"""答题器助手页面

功能：
- 复用共享 OCR 引擎（utils.ocr_engine）识别屏幕答题区域文字
- 模糊匹配本地题库，展示 Top5 答案及置信度
- 题库管理（增删改查、CSV 导入导出）
- 窗口锁定 + 区域框选（相对坐标持久化，窗口移动后自动重算）
"""

import json
import os
import threading

import flet as ft

from core.quiz_db import QuizDB
from utils.logger_setup import logger
from utils.ocr_engine import OCREngine, find_window_by_title
from utils.platform_utils import get_app_data_dir


class QuizAssistantPage(ft.Column):
    """答题器助手页面"""

    def __init__(self, data_manager, page):
        super().__init__()
        self.data_manager = data_manager
        self._page = page

        # 数据库
        app_data_dir = get_app_data_dir()
        db_path = os.path.join(app_data_dir, "quiz_bank.db")
        seed_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "quiz_bank_seed.csv")
        self.quiz_db = QuizDB(db_path, seed_file=seed_path)

        # OCR 引擎
        self.ocr_engine = OCREngine()

        # 窗口与区域状态
        self.custom_region = None          # 锁定的窗口区域 (left, top, right, bottom)
        self.locked_window_title = None
        self.quiz_region = None            # 答题识别区域 (left, top, right, bottom)
        self.selected_category = ""
        self.page_size = 50
        self.current_page = 1

        # UI 布局
        self.expand = True
        self.spacing = 10
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 窗口锁定卡片
        self.window_status_text = ft.Text("未锁定窗口", size=14, color=ft.Colors.OUTLINE)
        self.lock_window_btn = ft.ElevatedButton(
            "锁定游戏窗口", icon=ft.Icons.LOCK_OUTLINE,
            on_click=self._lock_window,
        )
        self.unlock_btn = ft.ElevatedButton(
            "解除锁定", icon=ft.Icons.LOCK_OPEN,
            on_click=self._unlock_window, visible=False, bgcolor=ft.Colors.RED_100,
        )

        # 区域选择
        self.region_status_text = ft.Text("未设置答题区域", size=14, color=ft.Colors.OUTLINE)
        self.select_region_btn = ft.ElevatedButton(
            "框选答题区域", icon=ft.Icons.CROP,
            on_click=self._start_select_region, disabled=True,
        )

        # 识别按钮
        self.recognize_btn = ft.ElevatedButton(
            "开始识别", icon=ft.Icons.SEARCH,
            on_click=self._recognize, disabled=True,
            bgcolor=ft.Colors.BLUE_100,
        )

        # OCR 结果展示
        self.ocr_result_text = ft.Text(
            "等待识别...", size=14, color=ft.Colors.ON_SURFACE,
            max_lines=5, overflow=ft.TextOverflow.ELLIPSIS,
        )

        # 匹配答案列表
        self.match_list = ft.ListView(spacing=6, expand=True)
        self.match_list.controls.append(
            ft.Text("识别后将显示匹配答案", size=13, color=ft.Colors.OUTLINE)
        )

        # 题库搜索
        self.search_field = ft.TextField(
            label="搜索问题、答案或分类",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_search_change,
            expand=True,
        )
        self.category_dropdown = ft.Dropdown(
            label="分类",
            value="全部分类",
            options=[ft.DropdownOption("全部分类")],
            on_select=self._on_category_change,
            width=150,
        )

        # 题库表格
        self.quiz_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("问题"), on_sort=lambda e: None),
                ft.DataColumn(ft.Text("答案")),
                ft.DataColumn(ft.Text("分类")),
                ft.DataColumn(ft.Text("命中"), numeric=True),
                ft.DataColumn(ft.Text("操作")),
            ],
            rows=[],
            column_spacing=20,
            horizontal_margin=10,
        )

        # 统计文本
        self.stats_text = ft.Text("题库：0 条", size=13, color=ft.Colors.OUTLINE)
        self.page_text = ft.Text("第 1 / 1 页", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        self.previous_page_btn = ft.IconButton(
            ft.Icons.CHEVRON_LEFT,
            tooltip="上一页",
            on_click=lambda e: self._change_page(-1),
        )
        self.next_page_btn = ft.IconButton(
            ft.Icons.CHEVRON_RIGHT,
            tooltip="下一页",
            on_click=lambda e: self._change_page(1),
        )

        # 题库操作按钮
        self.add_btn = ft.ElevatedButton(
            "添加", icon=ft.Icons.ADD, on_click=self._show_add_dialog,
        )
        self.import_btn = ft.ElevatedButton(
            "导入CSV", icon=ft.Icons.UPLOAD, on_click=self._import_csv,
        )
        self.export_btn = ft.ElevatedButton(
            "导出CSV", icon=ft.Icons.DOWNLOAD, on_click=self._export_csv,
        )

        # 组装布局
        self.controls = [
            ft.Column([
                ft.Text("答题器助手", size=26, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "框选游戏题目，识别文字并从本地题库快速匹配答案。",
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ], spacing=2),
            ft.Container(
                    content=ft.Column([
                        ft.Text("识别设置", size=16, weight=ft.FontWeight.BOLD),
                        ft.Row([
                            self.lock_window_btn,
                            self.unlock_btn,
                            self.window_status_text,
                        ], spacing=10),
                        ft.Row([
                            self.select_region_btn,
                            self.region_status_text,
                        ], spacing=10),
                        ft.Row([
                            self.recognize_btn,
                            ft.Text("识别完成后会显示最接近的 5 个答案", size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT),
                        ], spacing=10),
                    ], spacing=8),
                    padding=16,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                    border_radius=12,
            ),
            # 主内容区
            ft.Row([
                # 左侧：识别结果 + 匹配答案
                ft.Container(
                    content=ft.Column([
                        ft.Text("识别结果", size=16, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=self.ocr_result_text,
                            padding=10,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                            border_radius=8,
                        ),
                        ft.Divider(),
                        ft.Text("匹配答案", size=16, weight=ft.FontWeight.BOLD),
                        self.match_list,
                    ], spacing=8, expand=True),
                    expand=3,
                    padding=10,
                ),
                ft.VerticalDivider(width=1),
                # 右侧：题库管理
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("题库管理", size=16, weight=ft.FontWeight.BOLD),
                            self.stats_text,
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([self.search_field, self.category_dropdown], spacing=8),
                        ft.Row([
                            self.add_btn, self.import_btn, self.export_btn,
                        ], spacing=5),
                        ft.Container(
                            content=ft.Column([
                                self.quiz_table,
                            ], scroll=ft.ScrollMode.AUTO, expand=True),
                            expand=True,
                        ),
                        ft.Row([
                            ft.Text("每页 50 条", size=12, color=ft.Colors.OUTLINE),
                            ft.Row([
                                self.previous_page_btn,
                                self.page_text,
                                self.next_page_btn,
                            ], spacing=2),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ], spacing=8, expand=True),
                    expand=4,
                    padding=10,
                ),
            ], expand=True),
        ]

    # ------------------------------------------------------------------
    # 窗口锁定
    # ------------------------------------------------------------------
    def _lock_window(self, e=None):
        """锁定梦幻西游游戏窗口"""
        result = find_window_by_title("梦幻西游")
        if result is None:
            self._show_snackbar("未找到梦幻西游窗口")
            return

        title, region = result
        self.custom_region = region
        self.locked_window_title = title
        self.window_status_text.value = f"已锁定: {title}"
        self.window_status_text.color = ft.Colors.GREEN
        self.lock_window_btn.visible = False
        self.unlock_btn.visible = True
        self.select_region_btn.disabled = False

        # 尝试加载已保存的答题区域
        self._load_region_config()

        # 如果已有答题区域，启用识别按钮
        if self.quiz_region:
            self.recognize_btn.disabled = False
            self.region_status_text.value = (
                f"答题区域: ({self.quiz_region[0]}, {self.quiz_region[1]}) - "
                f"({self.quiz_region[2]}, {self.quiz_region[3]})"
            )
            self.region_status_text.color = ft.Colors.GREEN

        self._page.update()
        logger.info(f"答题器锁定窗口: {title}, 区域: {region}")

    def _unlock_window(self, e=None):
        """解除窗口锁定"""
        self.custom_region = None
        self.locked_window_title = None
        self.quiz_region = None
        self.window_status_text.value = "未锁定窗口"
        self.window_status_text.color = ft.Colors.OUTLINE
        self.region_status_text.value = "未设置答题区域"
        self.region_status_text.color = ft.Colors.OUTLINE
        self.lock_window_btn.visible = True
        self.unlock_btn.visible = False
        self.select_region_btn.disabled = True
        self.recognize_btn.disabled = True
        self._page.update()
        logger.info("答题器窗口锁定已解除")

    # ------------------------------------------------------------------
    # 区域框选
    # ------------------------------------------------------------------
    def _start_select_region(self, e=None):
        """启动区域框选（Tkinter 透明覆盖层）"""
        if not self.custom_region:
            self._show_snackbar("请先锁定游戏窗口")
            return
        t = threading.Thread(target=self._run_region_selection, daemon=True)
        t.start()

    def _run_region_selection(self):
        """运行区域框选逻辑"""
        import ctypes
        import tkinter as tk

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
        canvas.create_text(
            root.winfo_screenwidth() // 2, root.winfo_screenheight() // 2,
            text="按住鼠标左键拖动框选答题区域，按 ESC 取消",
            fill="white", font=("Microsoft YaHei", 16),
            anchor=tk.CENTER, tag="hint",
        )

        start_x = start_y = end_x = end_y = 0
        rect_id = None
        selected_region = None

        def on_press(event):
            nonlocal start_x, start_y, rect_id
            start_x, start_y = event.x, event.y
            canvas.delete("rect")
            rect_id = canvas.create_rectangle(
                start_x, start_y, start_x, start_y,
                outline="red", width=2, tag="rect"
            )

        def on_drag(event):
            nonlocal end_x, end_y, rect_id
            end_x, end_y = event.x, event.y
            canvas.delete("rect")
            rect_id = canvas.create_rectangle(
                start_x, start_y, end_x, end_y,
                outline="red", width=2, tag="rect"
            )

        def on_release(event):
            nonlocal end_x, end_y, selected_region
            end_x, end_y = event.x, event.y
            region = (min(start_x, end_x), min(start_y, end_y),
                      max(start_x, end_x), max(start_y, end_y))
            if region[2] - region[0] > 10 and region[3] - region[1] > 10:
                selected_region = region
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
        except Exception:
            pass

        if selected_region:
            self._save_quiz_region(selected_region)

    def _save_quiz_region(self, region):
        """保存答题区域（相对窗口偏移量，窗口移动后自动重算）"""
        config_dir = get_app_data_dir()
        config_path = os.path.join(config_dir, "quiz_region_config.json")

        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except Exception:
                pass

        if self.custom_region:
            window_left, window_top, _, _ = self.custom_region
            offset_x = region[0] - window_left
            offset_y = region[1] - window_top
            width = region[2] - region[0]
            height = region[3] - region[1]
            config["quiz_offset"] = (offset_x, offset_y, width, height)
            logger.info(f"答题区域相对偏移量已保存: ({offset_x}, {offset_y}, {width}, {height})")
        else:
            config["quiz_region"] = region

        config["locked_window_region"] = self.custom_region

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存答题区域配置失败: {e}")

        self.quiz_region = region
        self.recognize_btn.disabled = False
        self.region_status_text.value = (
            f"答题区域: ({region[0]}, {region[1]}) - ({region[2]}, {region[3]})"
        )
        self.region_status_text.color = ft.Colors.GREEN
        self._page.update()
        logger.info(f"答题区域已保存: {region}")

    def _load_region_config(self):
        """加载已保存的答题区域配置"""
        config_dir = get_app_data_dir()
        config_path = os.path.join(config_dir, "quiz_region_config.json")
        if not os.path.exists(config_path):
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if "quiz_offset" in config and self.custom_region:
                offset_x, offset_y, width, height = config["quiz_offset"]
                window_left, window_top, _, _ = self.custom_region
                self.quiz_region = (
                    window_left + offset_x,
                    window_top + offset_y,
                    window_left + offset_x + width,
                    window_top + offset_y + height,
                )
                logger.info(f"答题区域已从配置加载: {self.quiz_region}")
            elif "quiz_region" in config:
                self.quiz_region = config["quiz_region"]
                logger.info(f"答题区域已从配置加载(绝对坐标): {self.quiz_region}")
        except Exception as e:
            logger.error(f"加载答题区域配置失败: {e}")

    # ------------------------------------------------------------------
    # OCR 识别 + 模糊匹配
    # ------------------------------------------------------------------
    def _recognize(self, e=None):
        """识别答题区域文字并匹配题库"""
        if not self.quiz_region:
            self._show_snackbar("请先框选答题区域")
            return

        def _do_recognize():
            try:
                self.ocr_result_text.value = "正在识别..."
                self.ocr_result_text.color = ft.Colors.OUTLINE
                self._page.update()

                # OCR 识别
                texts = self.ocr_engine.recognize_text(self.quiz_region)
                recognized_text = " ".join(texts).strip() if texts else ""

                if not recognized_text:
                    self.ocr_result_text.value = "未识别到文字，请调整答题区域"
                    self.ocr_result_text.color = ft.Colors.RED
                    self.match_list.controls.clear()
                    self.match_list.controls.append(
                        ft.Text("无匹配结果", color=ft.Colors.OUTLINE)
                    )
                    self._page.update()
                    return

                # 显示识别结果
                self.ocr_result_text.value = recognized_text
                self.ocr_result_text.color = ft.Colors.ON_SURFACE
                logger.debug(f"答题器 OCR 识别结果: {recognized_text}")

                # 模糊匹配
                matches = self.quiz_db.fuzzy_match(recognized_text, limit=5, min_score=0.3)

                self.match_list.controls.clear()
                if not matches:
                    self.match_list.controls.append(
                        ft.Text("题库中未找到匹配题目", color=ft.Colors.OUTLINE)
                    )
                    # 提供快速添加入口
                    self.match_list.controls.append(
                        ft.ElevatedButton(
                            "添加此题目到题库", icon=ft.Icons.ADD,
                            on_click=lambda e: self._quick_add_question(recognized_text),
                        )
                    )
                else:
                    for i, (q, score) in enumerate(matches, 1):
                        confidence_color = (
                            ft.Colors.GREEN if score >= 0.8
                            else ft.Colors.ORANGE if score >= 0.5
                            else ft.Colors.RED
                        )
                        self.match_list.controls.append(
                            ft.Container(
                                content=ft.Column([
                                    ft.Row([
                                        ft.Text(f"{i}.", weight=ft.FontWeight.BOLD, width=20),
                                        ft.Text(f"{score*100:.0f}%",
                                                color=confidence_color, weight=ft.FontWeight.BOLD),
                                    ], spacing=5),
                                    ft.Text(f"问题: {q['question']}", size=13,
                                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Container(
                                        content=ft.Text(f"答案: {q['answer']}",
                                                        size=14, weight=ft.FontWeight.BOLD,
                                                        color=ft.Colors.PRIMARY),
                                        bgcolor=ft.Colors.PRIMARY_CONTAINER,
                                        padding=8,
                                        border_radius=6,
                                    ),
                                ], spacing=4),
                                padding=8,
                                border=ft.Border(
                                    top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                    bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                    left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                    right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                ),
                                border_radius=8,
                            )
                        )

                self._page.update()

            except Exception as ex:
                logger.error(f"答题器识别失败: {ex}")
                self.ocr_result_text.value = f"识别失败: {ex}"
                self.ocr_result_text.color = ft.Colors.RED
                self._page.update()

        threading.Thread(target=_do_recognize, daemon=True).start()

    # ------------------------------------------------------------------
    # 题库管理
    # ------------------------------------------------------------------
    def _on_search_change(self, e):
        """搜索框内容变化"""
        self.current_page = 1
        self._refresh_quiz_table()

    def _on_category_change(self, e):
        """切换题目分类。"""
        self.selected_category = "" if e.control.value == "全部分类" else e.control.value
        self.current_page = 1
        self._refresh_quiz_table()

    def _change_page(self, delta: int):
        self.current_page = max(1, self.current_page + delta)
        self._refresh_quiz_table()

    def _refresh_quiz_table(self, keyword: str = ""):
        """刷新题库表格"""
        keyword = keyword or (self.search_field.value or "").strip()
        filtered_total = self.quiz_db.count_questions(keyword, self.selected_category)
        page_count = max(1, (filtered_total + self.page_size - 1) // self.page_size)
        self.current_page = min(self.current_page, page_count)
        questions = self.quiz_db.query_questions(
            keyword=keyword,
            category=self.selected_category,
            limit=self.page_size,
            offset=(self.current_page - 1) * self.page_size,
        )

        self.quiz_table.rows.clear()
        for q in questions:
            self.quiz_table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(q["question"], max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS, width=200)),
                    ft.DataCell(ft.Text(q["answer"], max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS, width=150)),
                    ft.DataCell(ft.Text(q["category"] or "-", width=80)),
                    ft.DataCell(ft.Text(str(q["hit_count"]))),
                    ft.DataCell(ft.Row([
                        ft.IconButton(
                            ft.Icons.EDIT, icon_size=18,
                            tooltip="编辑",
                            on_click=lambda e, qid=q["id"]: self._show_edit_dialog(qid),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE, icon_size=18,
                            icon_color=ft.Colors.RED,
                            tooltip="删除",
                            on_click=lambda e, qid=q["id"]: self._delete_question(qid),
                        ),
                    ], spacing=0)),
                ])
            )

        # 更新统计
        stats = self.quiz_db.get_stats()
        self.stats_text.value = (
            f"题库：{stats['total']} 条 | 分类：{stats['categories']} | "
            f"总命中：{stats['total_hits']}"
        )
        categories = self.quiz_db.get_categories()
        current_category = self.category_dropdown.value or "全部分类"
        self.category_dropdown.options = [ft.DropdownOption("全部分类")] + [
            ft.DropdownOption(category) for category in categories
        ]
        if current_category not in ["全部分类", *categories]:
            current_category = "全部分类"
            self.selected_category = ""
        self.category_dropdown.value = current_category
        self.page_text.value = f"第 {self.current_page} / {page_count} 页 · {filtered_total} 条结果"
        self.previous_page_btn.disabled = self.current_page <= 1
        self.next_page_btn.disabled = self.current_page >= page_count

        self._page.update()

    def _show_add_dialog(self, e=None):
        """显示添加题目对话框"""
        self._show_question_dialog(None)

    def _quick_add_question(self, recognized_text: str):
        """快速添加识别到的题目"""
        self._show_question_dialog(None, default_question=recognized_text)

    def _show_edit_dialog(self, question_id: int):
        """显示编辑题目对话框"""
        self._show_question_dialog(question_id)

    def _show_question_dialog(self, question_id: int = None, default_question: str = ""):
        """显示添加/编辑题目对话框"""
        is_edit = question_id is not None

        # 查找现有题目
        existing = None
        if is_edit:
            existing = self.quiz_db.get_question(question_id)
            if not existing:
                self._show_snackbar("题目不存在")
                return

        question_field = ft.TextField(
            label="问题", multiline=True, min_lines=2, max_lines=4,
            value=existing["question"] if existing else default_question,
            expand=True,
        )
        answer_field = ft.TextField(
            label="答案", multiline=True, min_lines=2, max_lines=4,
            value=existing["answer"] if existing else "",
            expand=True,
        )
        category_field = ft.TextField(
            label="分类（可选）",
            value=existing["category"] if existing else "",
            expand=True,
        )

        def on_save(e):
            question = question_field.value.strip() if question_field.value else ""
            answer = answer_field.value.strip() if answer_field.value else ""
            category = category_field.value.strip() if category_field.value else ""

            if not question or not answer:
                self._show_snackbar("问题和答案不能为空")
                return

            try:
                if is_edit:
                    self.quiz_db.update_question(question_id, question, answer, category)
                    message = "题目已更新"
                else:
                    self.quiz_db.add_question(question, answer, category)
                    message = "题目已添加"
            except ValueError as ex:
                self._show_snackbar(str(ex))
                return

            self._page.pop_dialog()
            self._show_snackbar(message)
            self._refresh_quiz_table(self.search_field.value.strip() if self.search_field.value else "")

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑题目" if is_edit else "添加题目"),
            content=ft.Column([
                question_field, answer_field, category_field,
            ], tight=True, spacing=10, width=500),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.ElevatedButton("保存", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dialog)

    def _delete_question(self, question_id: int):
        """删除题目"""
        def on_confirm(e):
            self.quiz_db.delete_question(question_id)
            self._show_snackbar("题目已删除")
            self._page.pop_dialog()
            self._refresh_quiz_table(
                self.search_field.value.strip() if self.search_field.value else ""
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("确认删除"),
            content=ft.Text("确定要删除这道题目吗？"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.ElevatedButton("删除", on_click=on_confirm,
                                  bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dialog)

    async def _import_csv(self, e=None):
        """从 CSV 导入题库"""
        try:
            result = await self._page.pick_files(
                allow_multiple=False,
                allowed_extensions=["csv"],
            )
            if not result or not result.files:
                return

            filepath = result.files[0].path
            success, count = self.quiz_db.import_from_csv(filepath)
            if success:
                self._show_snackbar(f"成功导入 {count} 条题目")
                self._refresh_quiz_table()
            else:
                self._show_snackbar("导入失败")
        except Exception as ex:
            logger.error(f"导入题库失败: {ex}")
            self._show_snackbar(f"导入失败: {ex}")

    async def _export_csv(self, e=None):
        """导出题库到 CSV"""
        try:
            path = await self._page.save_file(
                dialog_title="导出题库",
                file_name="quiz_bank.csv",
                allowed_extensions=["csv"],
            )
            if not path:
                return

            count = self.quiz_db.export_to_csv(path)
            if count > 0:
                self._show_snackbar(f"已导出 {count} 条题目")
            else:
                self._show_snackbar("导出失败或题库为空")
        except Exception as ex:
            logger.error(f"导出题库失败: {ex}")
            self._show_snackbar(f"导出失败: {ex}")

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _show_snackbar(self, message: str):
        """显示提示消息"""
        self._page.show_dialog(
            ft.AlertDialog(
                content=ft.Text(message),
                actions=[ft.TextButton("确定", on_click=lambda e: self._page.pop_dialog())],
            )
        )

    def did_mount(self):
        """页面挂载后加载题库数据"""
        self._refresh_quiz_table()

    def cleanup(self):
        """清理页面资源"""
        try:
            self.ocr_engine.close()
        except Exception:
            pass
        logger.debug("QuizAssistantPage 资源已清理")
