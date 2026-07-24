import flet as ft
import os
from growth_db import GrowthDB
from platform_utils import get_app_data_dir


class GrowthPage(ft.Column):
    def __init__(self, data_manager, page):
        super().__init__()
        self.data_manager = data_manager
        self._page = page
        
        app_data_dir = get_app_data_dir()
        db_path = os.path.join(app_data_dir, "growth.db")
        self.db = GrowthDB(db_path)
        
        self.expand = True
        self.spacing = 10
        self.scroll = ft.ScrollMode.AUTO
        
        self.selected_role = None
        self.growth_data = None
        
        self.cur_fields = {}
        self.tar_fields = {}
        
        self._build_ui()

    def did_mount(self):
        self._load_role_options()

    def _build_ui(self):
        self.role_dropdown = ft.Dropdown(
            label="选择角色",
            width=200,
            on_select=self._on_role_change,
        )
        
        self.empty_state = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.INBOX, size=64, color=ft.Colors.OUTLINE),
                    ft.Text("请先在【账号管理】中添加角色", size=16, color=ft.Colors.OUTLINE),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment(0, 0),
            expand=True,
        )
        
        self.content_container = ft.Column(expand=True, spacing=10)
        
        self.controls = [
            ft.Row([self.role_dropdown], alignment=ft.MainAxisAlignment.START),
            ft.Divider(),
            ft.Container(
                content=ft.Stack([self.empty_state, self.content_container]),
                expand=True,
            ),
        ]

    def _load_role_options(self):
        accounts = self.data_manager.get_all_accounts()
        role_names = [acc['username'] for acc in accounts]
        
        self.role_dropdown.options = [ft.DropdownOption(name) for name in role_names]
        
        if role_names:
            self.selected_role = role_names[0]
            self.role_dropdown.value = role_names[0]
            self.empty_state.visible = False
            self.content_container.visible = True
            self._load_role_data()
        else:
            self.selected_role = None
            self.role_dropdown.value = None
            self.empty_state.visible = True
            self.content_container.visible = False
        
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_role_change(self, e):
        self.selected_role = e.control.value
        self._load_role_data()

    def _load_role_data(self):
        if not self.selected_role:
            return
        
        self.growth_data = self.db.get_role_growth(self.selected_role)
        if not self.growth_data:
            self.growth_data = {
                'role_name': self.selected_role,
                'cur_level': 0, 'cur_hp': 0, 'cur_mp': 0,
                'cur_damage': 0, 'cur_magic_damage': 0,
                'cur_defense': 0, 'cur_magic_defense': 0, 'cur_speed': 0,
                'cur_atk_cult': 0, 'cur_def_cult': 0,
                'cur_magic_atk_cult': 0, 'cur_magic_def_cult': 0,
                'cur_main_skill': 0,
                'tar_level': 0, 'tar_hp': 0, 'tar_mp': 0,
                'tar_damage': 0, 'tar_magic_damage': 0,
                'tar_defense': 0, 'tar_magic_defense': 0, 'tar_speed': 0,
                'tar_atk_cult': 0, 'tar_def_cult': 0,
                'tar_magic_atk_cult': 0, 'tar_magic_def_cult': 0,
                'tar_main_skill': 0,
                'equip_weapon': '', 'equip_head': '', 'equip_body': '',
                'equip_belt': '', 'equip_shoes': '', 'equip_necklace': '',
            }
        
        self.cur_fields = {}
        self.tar_fields = {}
        
        self._build_content()
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_content(self):
        self.content_container.controls.clear()
        
        self.content_container.controls.append(
            ft.Text(f"📊 {self.selected_role} 的养成规划", size=20, weight=ft.FontWeight.BOLD)
        )
        
        is_mobile = self._page.width < 600
        
        if is_mobile:
            self.content_container.controls.append(self._build_attributes_panel_mobile())
        else:
            self.content_container.controls.append(self._build_attributes_panel_desktop())
        
        self.content_container.controls.append(self._build_progress_section())
        self.content_container.controls.append(self._build_equipment_section())
        self.content_container.controls.append(self._build_action_bar())

    def _build_attributes_panel_desktop(self):
        current_panel = self._build_current_panel()
        target_panel = self._build_target_panel()
        
        return ft.Row([current_panel, target_panel], spacing=20, expand=True)

    def _build_attributes_panel_mobile(self):
        current_panel = self._build_current_panel()
        target_panel = self._build_target_panel()
        
        return ft.Column([current_panel, target_panel], spacing=20)

    def _build_current_panel(self):
        attr_groups = [
            ("基础属性", [
                ("等级", "level"),
                ("气血", "hp"),
                ("魔法", "mp"),
            ]),
            ("攻击属性", [
                ("伤害", "damage"),
                ("法伤", "magic_damage"),
            ]),
            ("防御属性", [
                ("防御", "defense"),
                ("法防", "magic_defense"),
                ("速度", "speed"),
            ]),
            ("修炼属性", [
                ("攻修", "atk_cult"),
                ("防修", "def_cult"),
                ("法攻修", "magic_atk_cult"),
                ("法防修", "magic_def_cult"),
            ]),
            ("技能", [
                ("主技能", "main_skill"),
            ]),
        ]
        
        controls = [ft.Text("当前属性", size=16, weight=ft.FontWeight.BOLD), ft.Divider()]
        
        for group_name, attrs in attr_groups:
            controls.append(ft.Text(group_name, size=12, color=ft.Colors.GREY))
            for label, key in attrs:
                field = ft.TextField(
                    label=label,
                    value=str(self.growth_data.get(f"cur_{key}", 0)) if self.growth_data.get(f"cur_{key}", 0) else "",
                    width=100,
                    input_filter=ft.NumbersOnlyInputFilter(),
                )
                self.cur_fields[key] = field
                controls.append(ft.Row([
                    ft.Text(label, width=50),
                    field,
                ], spacing=10, alignment=ft.CrossAxisAlignment.CENTER))
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column(controls, spacing=5),
                padding=15,
            ),
            expand=True,
        )

    def _build_target_panel(self):
        attr_groups = [
            ("基础属性", [
                ("等级", "level"),
                ("气血", "hp"),
                ("魔法", "mp"),
            ]),
            ("攻击属性", [
                ("伤害", "damage"),
                ("法伤", "magic_damage"),
            ]),
            ("防御属性", [
                ("防御", "defense"),
                ("法防", "magic_defense"),
                ("速度", "speed"),
            ]),
            ("修炼属性", [
                ("攻修", "atk_cult"),
                ("防修", "def_cult"),
                ("法攻修", "magic_atk_cult"),
                ("法防修", "magic_def_cult"),
            ]),
            ("技能", [
                ("主技能", "main_skill"),
            ]),
        ]
        
        controls = [
            ft.Row([
                ft.Text("目标属性", size=16, weight=ft.FontWeight.BOLD),
                ft.IconButton(
                    icon=ft.Icons.COPY,
                    tooltip="复制当前到目标",
                    on_click=self._copy_current_to_target,
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider()
        ]
        
        for group_name, attrs in attr_groups:
            controls.append(ft.Text(group_name, size=12, color=ft.Colors.GREY))
            for label, key in attrs:
                cur_val = self.growth_data.get(f"cur_{key}", 0)
                tar_val = self.growth_data.get(f"tar_{key}", 0)
                diff = tar_val - cur_val
                
                diff_color = ft.Colors.GREEN if diff > 0 else (ft.Colors.RED if diff < 0 else ft.Colors.GREY)
                diff_text = f"+{diff}" if diff > 0 else str(diff)
                
                def copy_to_target(e, k=key):
                    cur_v = self.growth_data.get(f"cur_{k}", 0)
                    self.tar_fields[k].value = str(cur_v)
                    self.tar_fields[k].update()
                
                tar_field = ft.TextField(
                    label="",
                    value=str(tar_val) if tar_val else "",
                    width=100,
                    input_filter=ft.NumbersOnlyInputFilter(),
                )
                self.tar_fields[key] = tar_field
                
                controls.append(ft.Row([
                    ft.Text(label, width=50),
                    ft.IconButton(
                        icon=ft.Icons.ARROW_RIGHT,
                        icon_size=16,
                        tooltip="从当前复制",
                        on_click=copy_to_target,
                    ),
                    tar_field,
                    ft.Text(diff_text, size=14, weight=ft.FontWeight.BOLD, color=diff_color, width=50),
                ], spacing=5, alignment=ft.CrossAxisAlignment.CENTER))
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column(controls, spacing=5),
                padding=15,
            ),
            expand=True,
        )

    def _build_progress_section(self):
        progress_items = []
        total_progress = 0
        count = 0
        priorities = []
        
        attr_map = {
            "等级": "level", "气血": "hp", "魔法": "mp",
            "伤害": "damage", "法伤": "magic_damage",
            "防御": "defense", "法防": "magic_defense", "速度": "speed",
            "攻修": "atk_cult", "防修": "def_cult",
            "法攻修": "magic_atk_cult", "法防修": "magic_def_cult",
            "主技能": "main_skill",
        }
        
        for label, key in attr_map.items():
            cur_val = self.growth_data.get(f"cur_{key}", 0)
            tar_val = self.growth_data.get(f"tar_{key}", 0)
            
            if tar_val > cur_val and cur_val > 0:
                progress = min(100, int((cur_val / tar_val) * 100))
                progress_items.append((label, cur_val, tar_val, progress))
                total_progress += progress
                count += 1
                priorities.append((label, tar_val - cur_val))
        
        priorities.sort(key=lambda x: x[1], reverse=True)
        priority_text = ", ".join([f"{p[0]}(+{p[1]})" for p in priorities[:3]])
        
        overall_progress = int(total_progress / count) if count > 0 else 0
        
        progress_bar_color = ft.Colors.GREEN if overall_progress >= 100 else (
            ft.Colors.BLUE if overall_progress >= 50 else (
                ft.Colors.ORANGE if overall_progress > 0 else ft.Colors.GREY
            )
        )
        
        progress_list = []
        for label, cur, tar, progress in progress_items:
            bar_color = ft.Colors.GREEN if progress >= 100 else (
                ft.Colors.BLUE if progress >= 50 else (
                    ft.Colors.ORANGE if progress > 0 else ft.Colors.GREY
                )
            )
            progress_list.append(ft.Row([
                ft.Text(f"{label}: {cur}→{tar}", size=12, width=120),
                ft.ProgressBar(value=progress / 100, width=150, color=bar_color),
                ft.Text(f"{progress}%", size=12, width=40),
            ], alignment=ft.CrossAxisAlignment.CENTER, spacing=10))
        
        if not progress_items:
            progress_list.append(ft.Text("暂无目标设置，请先设置目标属性", color=ft.Colors.GREY))
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("📈 成长进度概览", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Row([
                        ft.Text(f"整体完成度: {overall_progress}%", size=14),
                        ft.ProgressBar(value=overall_progress / 100, width=200, color=progress_bar_color),
                    ], alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    ft.Row([
                        ft.Text("🔥 优先提升:", size=14, color=ft.Colors.ORANGE),
                        ft.Text(priority_text if priority_text else "无", size=14),
                    ], spacing=5),
                    ft.Column(progress_list, spacing=5),
                ], spacing=8),
                padding=15,
            ),
        )

    def _build_equipment_section(self):
        self.equip_fields = {}
        
        equip_items = [
            ("武器", "equip_weapon"),
            ("头盔", "equip_head"),
            ("铠甲", "equip_body"),
            ("腰带", "equip_belt"),
            ("鞋子", "equip_shoes"),
            ("项链", "equip_necklace"),
        ]
        
        row1 = []
        row2 = []
        
        for i, (label, key) in enumerate(equip_items):
            field = ft.TextField(
                label=label,
                value=self.growth_data.get(key, ""),
                expand=True,
            )
            self.equip_fields[key] = field
            if i < 3:
                row1.append(field)
            else:
                row2.append(field)
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("⚔️ 装备简记", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Row(row1, spacing=10),
                    ft.Row(row2, spacing=10),
                ], spacing=8),
                padding=15,
            ),
        )

    def _build_action_bar(self):
        return ft.Row([
            ft.Button("保存属性", icon=ft.Icons.SAVE, on_click=self._save_data),
            ft.Button("复制当前到目标", icon=ft.Icons.COPY, on_click=self._copy_current_to_target),
            ft.Button("清空目标", icon=ft.Icons.CLEAR, on_click=self._clear_target),
        ], spacing=10)

    def _save_data(self, e):
        data = {'role_name': self.selected_role}
        
        attr_keys = [
            'level', 'hp', 'mp', 'damage', 'magic_damage',
            'defense', 'magic_defense', 'speed',
            'atk_cult', 'def_cult', 'magic_atk_cult', 'magic_def_cult',
            'main_skill',
        ]
        
        for key in attr_keys:
            cur_field = self.cur_fields.get(key)
            tar_field = self.tar_fields.get(key)
            
            if cur_field is None or tar_field is None:
                continue
            
            cur_val = int(cur_field.value) if cur_field.value else 0
            tar_val = int(tar_field.value) if tar_field.value else 0
            
            data[f"cur_{key}"] = cur_val
            data[f"tar_{key}"] = tar_val
            
            if key.endswith('_cult'):
                if cur_val > 25:
                    self._page.show_dialog(ft.SnackBar(content=ft.Text(f"{key}当前值不能超过25")))
                    return
                if tar_val > 25:
                    self._page.show_dialog(ft.SnackBar(content=ft.Text(f"{key}目标值不能超过25")))
                    return
        
        equip_keys = ['equip_weapon', 'equip_head', 'equip_body', 'equip_belt', 'equip_shoes', 'equip_necklace']
        for key in equip_keys:
            field = self.equip_fields.get(key)
            data[key] = field.value if field else ""
        
        self.db.upsert_role_growth(data)
        self._load_role_data()
        self._page.show_dialog(ft.SnackBar(content=ft.Text("已保存")))

    def _copy_current_to_target(self, e):
        attr_keys = [
            'level', 'hp', 'mp', 'damage', 'magic_damage',
            'defense', 'magic_defense', 'speed',
            'atk_cult', 'def_cult', 'magic_atk_cult', 'magic_def_cult',
            'main_skill',
        ]
        
        for key in attr_keys:
            cur_field = self.cur_fields.get(key)
            tar_field = self.tar_fields.get(key)
            
            if cur_field and tar_field:
                tar_field.value = cur_field.value
                tar_field.update()
        
        self._load_role_data()
        self._page.show_dialog(ft.SnackBar(content=ft.Text("已将当前属性复制到目标")))

    def _clear_target(self, e):
        def confirm_clear(e):
            attr_keys = [
                'level', 'hp', 'mp', 'damage', 'magic_damage',
                'defense', 'magic_defense', 'speed',
                'atk_cult', 'def_cult', 'magic_atk_cult', 'magic_def_cult',
                'main_skill',
            ]
            
            for key in attr_keys:
                tar_field = self.tar_fields.get(key)
                if tar_field:
                    tar_field.value = ""
                    tar_field.update()
            
            self._page.pop_dialog()
            self._load_role_data()
            self._page.show_dialog(ft.SnackBar(content=ft.Text("已清空所有目标")))
        
        dialog = ft.AlertDialog(
            title=ft.Text("确认清空"),
            content=ft.Text("确定要清空所有目标属性吗？此操作不可恢复。"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("清空", bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR, on_click=confirm_clear),
            ],
        )
        self._page.show_dialog(dialog)