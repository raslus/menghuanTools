import flet as ft
import os
from core.growth_db import GrowthDB
from utils.platform_utils import get_app_data_dir


EQUIPMENT_SLOTS = {
    "weapon": ("武器", ft.Icons.GAVEL, ["伤害", "命中"]),
    "head": ("头部", ft.Icons.SPORTS_MARTIAL_ARTS, ["防御", "魔法"]),
    "body": ("衣甲", ft.Icons.SHIELD, ["防御"]),
    "belt": ("腰带", ft.Icons.LINE_WEIGHT, ["防御", "气血"]),
    "shoes": ("鞋子", ft.Icons.DIRECTIONS_RUN, ["防御", "敏捷"]),
    "necklace": ("项链", ft.Icons.LINK, ["灵力"]),
    "ring": ("戒指", ft.Icons.CIRCLE_OUTLINED, ["伤害", "防御"]),
    "earring": ("耳饰", ft.Icons.HEARING, ["法术伤害", "法术防御"]),
    "bracelet": ("手镯", ft.Icons.WATCH, ["抵抗封印"]),
    "pendant": ("佩饰", ft.Icons.DIAMOND_OUTLINED, ["速度"]),
}

ACCESSORY_SLOTS = {"ring", "earring", "bracelet", "pendant"}
BONUS_ATTRIBUTES = ["无", "体质", "魔力", "力量", "耐力", "敏捷"]
FRONT_ACCESSORY_ATTRIBUTES = ["无", "伤害", "法术伤害", "固定伤害", "速度", "封印命中", "物理暴击", "法术暴击"]
BACK_ACCESSORY_ATTRIBUTES = ["无", "气血", "防御", "法术防御", "抵抗封印", "气血回复"]
SPECIAL_SKILLS = ["无", "罗汉金钟", "晶清诀", "玉清诀", "水清诀", "笑里藏刀", "破血狂攻", "弱点击破", "破碎无双", "四海升平", "慈航普度", "野兽之力", "流云诀", "凝滞术", "其他"]
SPECIAL_EFFECTS = ["无", "愤怒", "简易", "无级别限制", "永不磨损", "神农", "精致", "暴怒", "再生", "迷踪", "珍宝", "狩猎", "绝杀", "专注", "易修理", "其他"]
STAT_LABELS = {
    "hp": "气血", "mp": "魔法", "damage": "伤害", "magic_damage": "法伤",
    "defense": "防御", "magic_defense": "法防", "speed": "速度",
}
DISPLAY_STAT_TO_KEY = {
    "气血": "hp", "魔法": "mp", "伤害": "damage", "法术伤害": "magic_damage",
    "防御": "defense", "法术防御": "magic_defense", "速度": "speed",
}
JADE_ATTRIBUTES = ["无", "气血", "防御", "伤害", "速度", "法术伤害", "法术防御", "固定伤害", "封印命中", "抵抗封印", "治疗能力", "物理暴击", "法术暴击", "固伤暴击"]
JADE_CORE_ATTRIBUTES = ["无", "抗封几率", "抗物暴几率", "抗法暴几率", "气血回复效果"]


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
        self.workspace_tab_index = 0
        
        self.cur_fields = {}
        self.tar_fields = {}
        self.diff_texts = {}
        self.advice_container = ft.Container()
        
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
            ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text("养成规划", size=26, weight=ft.FontWeight.BOLD),
                        ft.Text("从当前面板出发，管理装备系统并形成可执行的提升目标", color=ft.Colors.ON_SURFACE_VARIANT),
                    ], spacing=2, expand=True),
                    ft.Icon(ft.Icons.PERSON_SEARCH, color=ft.Colors.PRIMARY),
                    self.role_dropdown,
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=16,
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                border_radius=12,
            ),
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

        self.equipment_data = self.db.get_role_equipment(self.selected_role)
        self.system_data = self.db.get_role_growth_system(self.selected_role)
        legacy_keys = {
            "weapon": "equip_weapon", "head": "equip_head", "body": "equip_body",
            "belt": "equip_belt", "shoes": "equip_shoes", "necklace": "equip_necklace",
        }
        for slot, old_key in legacy_keys.items():
            old_note = self.growth_data.get(old_key, "")
            if old_note and slot not in self.equipment_data:
                self.equipment_data[slot] = {"legacy_note": old_note}
        
        self.cur_fields = {}
        self.tar_fields = {}
        self.diff_texts = {}
        
        self._build_content()
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_content(self):
        self.content_container.controls.clear()
        
        self.content_container.controls.append(
            ft.Text(f"{self.selected_role} 的成长目标", size=20, weight=ft.FontWeight.BOLD)
        )
        
        current_view = ft.Column(
            [self._build_current_panel(), self._build_current_workflow_hint()],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )
        equipment_view = ft.Column(
            [self._build_equipment_section(), self._build_linked_stats_section()],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )
        planning_view = ft.Column(
            [self._build_target_panel(), self._build_progress_section(), self._build_growth_advice_section()],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )
        tabs_row = ft.Row(spacing=8)

        def switch_tab(index):
            self.workspace_tab_index = index
            current_view.visible = index == 0
            equipment_view.visible = index == 1
            planning_view.visible = index == 2
            build_tabs()
            self.update()

        def build_tabs():
            tabs_row.controls = [
                ft.Button("当前状态", icon=ft.Icons.SPEED, on_click=lambda e: switch_tab(0),
                          bgcolor=ft.Colors.PRIMARY_CONTAINER if self.workspace_tab_index == 0 else None),
                ft.Button("装备与玉魄", icon=ft.Icons.SHIELD, on_click=lambda e: switch_tab(1),
                          bgcolor=ft.Colors.PRIMARY_CONTAINER if self.workspace_tab_index == 1 else None),
                ft.Button("目标与建议", icon=ft.Icons.FLAG, on_click=lambda e: switch_tab(2),
                          bgcolor=ft.Colors.PRIMARY_CONTAINER if self.workspace_tab_index == 2 else None),
            ]

        current_view.visible = self.workspace_tab_index == 0
        equipment_view.visible = self.workspace_tab_index == 1
        planning_view.visible = self.workspace_tab_index == 2
        build_tabs()
        self.content_container.controls.append(ft.Row([
            tabs_row,
            ft.Container(expand=True),
            self._build_action_bar(),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        self.content_container.controls.append(ft.Stack([current_view, equipment_view, planning_view], expand=True))

    def _build_attributes_panel_desktop(self):
        current_panel = self._build_current_panel()
        target_panel = self._build_target_panel()
        
        return ft.Row([current_panel, target_panel], spacing=20, expand=True)

    def _build_current_workflow_hint(self):
        calibrated = bool(self.system_data.get("calibrated"))
        steps = [
            ("1", "核对当前面板", "按游戏内显示填写人物属性、修炼与主技能"),
            ("2", "录入装备与玉魄", "选择十个装备部位和命魂之玉的实际属性"),
            ("3", "校准并设定目标", "首次反推基础值，之后更换方案即可联动重算"),
        ]
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.ROUTE, color=ft.Colors.PRIMARY), ft.Text("推荐使用顺序", size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.Text("基础值已校准" if calibrated else "尚未校准", color=ft.Colors.GREEN if calibrated else ft.Colors.ORANGE)]),
                ft.Row([
                    ft.Container(
                        content=ft.Row([ft.Container(ft.Text(number, weight=ft.FontWeight.BOLD), width=34, height=34, alignment=ft.Alignment.CENTER, bgcolor=ft.Colors.PRIMARY_CONTAINER, border_radius=17), ft.Column([ft.Text(title, weight=ft.FontWeight.BOLD), ft.Text(description, size=11, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=2)], spacing=10),
                        padding=10, expand=True,
                    ) for number, title, description in steps
                ], spacing=8),
            ], spacing=8),
            padding=14, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=12,
        )

    def _build_attributes_panel_mobile(self):
        current_panel = self._build_current_panel()
        target_panel = self._build_target_panel()
        
        return ft.Column([current_panel, target_panel], spacing=20)

    def _build_current_panel(self):
        attr_groups = [
            ("人物面板", [("等级", "level"), ("气血", "hp"), ("魔法", "mp"), ("伤害", "damage"), ("法伤", "magic_damage"), ("防御", "defense"), ("法防", "magic_defense"), ("速度", "speed")]),
            ("修炼与技能", [("攻修", "atk_cult"), ("防修", "def_cult"), ("法攻修", "magic_atk_cult"), ("法防修", "magic_def_cult"), ("主技能", "main_skill")]),
        ]
        controls = [
            ft.Row([ft.Icon(ft.Icons.SPEED, color=ft.Colors.PRIMARY), ft.Column([ft.Text("当前状态", size=18, weight=ft.FontWeight.BOLD), ft.Text("填写游戏内实际面板；完成装备录入后进行一次基础校准", size=11, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1)]),
            ft.Divider(),
        ]
        for group_name, attrs in attr_groups:
            fields = []
            for label, key in attrs:
                field = ft.TextField(
                    label=label,
                    value=str(self.growth_data.get(f"cur_{key}", 0)) if self.growth_data.get(f"cur_{key}", 0) else "",
                    width=142,
                    input_filter=ft.NumbersOnlyInputFilter(),
                    on_change=self._on_attribute_change,
                )
                self.cur_fields[key] = field
                fields.append(field)
            controls.append(ft.Container(
                content=ft.Column([ft.Text(group_name, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY), ft.Row(fields, spacing=10, wrap=True)], spacing=8),
                padding=12, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=10,
            ))
        return ft.Card(
            content=ft.Container(content=ft.Column(controls, spacing=10), padding=18),
        )

    def _build_target_panel(self):
        attr_groups = [
            ("人物面板目标", [("等级", "level"), ("气血", "hp"), ("魔法", "mp"), ("伤害", "damage"), ("法伤", "magic_damage"), ("防御", "defense"), ("法防", "magic_defense"), ("速度", "speed")]),
            ("修炼与技能目标", [("攻修", "atk_cult"), ("防修", "def_cult"), ("法攻修", "magic_atk_cult"), ("法防修", "magic_def_cult"), ("主技能", "main_skill")]),
        ]
        controls = [
            ft.Row([
                ft.Column([ft.Text("目标属性", size=18, weight=ft.FontWeight.BOLD), ft.Text("只填写需要提升的目标，差值会自动进入建议", size=11, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=1, expand=True),
                ft.Button("以当前值起步", icon=ft.Icons.COPY, on_click=self._copy_current_to_target),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider()
        ]
        for group_name, attrs in attr_groups:
            field_cards = []
            for label, key in attrs:
                cur_val = self.growth_data.get(f"cur_{key}", 0)
                tar_val = self.growth_data.get(f"tar_{key}", 0)
                diff = tar_val - cur_val
                
                diff_color = ft.Colors.GREEN if diff > 0 else (ft.Colors.RED if diff < 0 else ft.Colors.GREY)
                diff_text = f"+{diff}" if diff > 0 else str(diff)
                
                def copy_to_target(e, k=key):
                    cur_v = self._field_number(self.cur_fields, k)
                    self.tar_fields[k].value = str(cur_v)
                    self.tar_fields[k].update()
                    self._on_attribute_change()
                
                tar_field = ft.TextField(
                    label=label,
                    value=str(tar_val) if tar_val else "",
                    width=142,
                    input_filter=ft.NumbersOnlyInputFilter(),
                    on_change=self._on_attribute_change,
                )
                self.tar_fields[key] = tar_field
                diff_control = ft.Text(diff_text, size=13, weight=ft.FontWeight.BOLD, color=diff_color)
                self.diff_texts[key] = diff_control
                field_cards.append(ft.Container(
                    content=ft.Column([tar_field, ft.Row([ft.Text(f"当前 {cur_val}", size=11, color=ft.Colors.OUTLINE), diff_control, ft.IconButton(ft.Icons.ARROW_FORWARD, icon_size=14, tooltip="使用当前值", on_click=copy_to_target)], spacing=5)], spacing=2),
                    width=190, padding=8, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=10,
                ))
            controls.append(ft.Column([ft.Text(group_name, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY), ft.Row(field_cards, spacing=8, wrap=True)], spacing=7))
        return ft.Card(
            content=ft.Container(content=ft.Column(controls, spacing=12), padding=18),
        )

    def _field_number(self, group, key):
        field = group.get(key)
        try:
            return int(field.value) if field and field.value else 0
        except (TypeError, ValueError):
            return 0

    def _refresh_growth_advice(self, e=None):
        if not self.advice_container:
            return
        self.advice_container.content = self._build_advice_content()
        try:
            self.advice_container.update()
        except RuntimeError:
            pass

    def _on_attribute_change(self, e=None):
        for key, control in self.diff_texts.items():
            diff = self._field_number(self.tar_fields, key) - self._field_number(self.cur_fields, key)
            control.value = f"+{diff}" if diff > 0 else str(diff)
            control.color = ft.Colors.GREEN if diff > 0 else (ft.Colors.RED if diff < 0 else ft.Colors.GREY)
            try:
                control.update()
            except RuntimeError:
                pass
        self._refresh_growth_advice()
        if e is not None and self.system_data.get("calibrated") and e.control is self.cur_fields.get("main_skill"):
            self._apply_linked_current_stats(show_message=False)

    def _build_growth_advice_section(self):
        self.advice_container = ft.Container(
            content=self._build_advice_content(),
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=12,
        )
        return self.advice_container

    def _build_advice_content(self):
        labels = {
            "level": "等级", "hp": "气血", "mp": "魔法", "damage": "伤害",
            "magic_damage": "法伤", "defense": "防御", "magic_defense": "法防",
            "speed": "速度", "atk_cult": "攻修", "def_cult": "防修",
            "magic_atk_cult": "法攻修", "magic_def_cult": "法防修", "main_skill": "主技能",
        }
        values = {
            key: (self._field_number(self.cur_fields, key), self._field_number(self.tar_fields, key))
            for key in labels
        }
        gaps = {key: target - current for key, (current, target) in values.items() if target > current}
        if not gaps:
            return ft.Column([
                ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.PRIMARY), ft.Text("养成建议", size=18, weight=ft.FontWeight.BOLD)]),
                ft.Text("设置高于当前值的目标后，将按等级、修炼和装备系统生成建议。", color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=8)

        target_level = values["level"][1] or values["level"][0]
        common_cult_cap = None
        if target_level:
            common_cult_cap = 25
            for level, cap in ((69, 9), (89, 13), (109, 17), (129, 20)):
                if target_level <= level:
                    common_cult_cap = cap
                    break

        stages = []
        if gaps.get("level", 0) > 0:
            stages.append(("1 · 等级门槛", f"先完成 {values['level'][0]} → {values['level'][1]} 级；等级会影响技能、修炼和装备等级的可选范围。"))
        if gaps.get("main_skill", 0) > 0:
            stages.append(("2 · 门派技能", f"主技能尚差 {gaps['main_skill']} 级。优先补主技能，再评估面板属性；不同门派技能作用不同，以游戏内说明为准。"))

        cultivation_gaps = [(labels[key], gap, values[key][1]) for key, gap in gaps.items() if key.endswith("_cult")]
        if cultivation_gaps:
            over_cap = [name for name, _, target in cultivation_gaps if common_cult_cap is not None and target > common_cult_cap]
            detail = "、".join(f"{name}+{gap}" for name, gap, _ in cultivation_gaps)
            note = (
                f"当前目标等级常见修炼档位上限约为 {common_cult_cap}。"
                if common_cult_cap is not None
                else "请先填写人物等级，才能核对常见修炼档位。"
            )
            if over_cap:
                note += f" { '、'.join(over_cap) } 超出该常见档位；飞升等情况存在例外，请以角色实际修炼上限为准。"
            stages.append(("3 · 人物修炼", f"需要提升：{detail}。{note}"))

        equipment_advice = []
        if gaps.get("damage"):
            equipment_advice.append("伤害：优先核查武器基础伤害/命中、附加属性，以及武器和头部的伤害向宝石/符石方案")
        if gaps.get("magic_damage") or gaps.get("magic_defense") or gaps.get("mp"):
            equipment_advice.append("法系面板：重点核查项链灵力、衣甲/项链相关宝石、前排灵饰法伤/法暴与门派技能")
        if gaps.get("defense"):
            equipment_advice.append("防御：重点核查铠甲、头盔基础防御，防御向宝石，以及后排灵饰防御词条")
        if gaps.get("hp"):
            equipment_advice.append("气血：重点核查腰带/衣甲、气血向宝石、后排灵饰气血与强身等基础系统")
        if gaps.get("speed"):
            equipment_advice.append("速度：重点核查鞋子、腰带的速度向宝石，前排灵饰速度词条及敏捷属性")
        if equipment_advice:
            stages.append(("4 · 装备与宝石", "；".join(equipment_advice) + "。不要把临时符属性计入长期目标。"))

        stages.append(("5 · 交叉系统复核", "检查四件灵饰（戒指、耳饰、手镯、佩饰）、符石组合、套装/特技、经脉与神器。它们可能改变输出或生存效果，但不一定全部直接反映在面板数值中。"))

        gap_chips = [
            ft.Container(
                content=ft.Text(f"{labels[key]} +{gap}", size=12, weight=ft.FontWeight.BOLD),
                padding=8,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                border_radius=16,
            )
            for key, gap in sorted(gaps.items(), key=lambda item: item[1], reverse=True)
        ]
        return ft.Column([
            ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.PRIMARY), ft.Text("养成路径建议", size=18, weight=ft.FontWeight.BOLD)]),
            ft.Row(gap_chips, spacing=8, wrap=True),
            *[
                ft.Container(
                    content=ft.Column([
                        ft.Text(title, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                        ft.Text(text, color=ft.Colors.ON_SURFACE_VARIANT),
                    ], spacing=3),
                    padding=ft.Padding.only(bottom=8),
                )
                for title, text in stages
            ],
            ft.Text("说明：建议按公开通用规则生成，不包含门派、经脉、装备等级和预算等个体条件，最终以游戏内实时数值为准。", size=11, color=ft.Colors.OUTLINE),
        ], spacing=8)

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
        self.equipment_grid = ft.Column(spacing=10)
        self._refresh_equipment_grid()
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Column([
                            ft.Text("当前装备", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text("直接选择部位属性，六件装备与四件灵饰统一管理", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ], spacing=2),
                        ft.Button("清空全部", icon=ft.Icons.DELETE_SWEEP, on_click=self._clear_all_equipment),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Divider(),
                    self.equipment_grid,
                    ft.Text("提示：这里记录的是当前生效装备；符石、套装、特技等非面板效果会单独显示，旧版文字记录保留在对应部位的备注中。", size=11, color=ft.Colors.OUTLINE),
                ], spacing=8),
                padding=18,
            ),
        )

    def _capture_link_controls(self):
        if hasattr(self, "manual_adjust_fields"):
            self.system_data["manual_adjustments"] = {
                key: int(field.value) if field.value not in (None, "", "-") else 0
                for key, field in self.manual_adjust_fields.items()
            }
        if hasattr(self, "skill_coefficient_fields"):
            coefficients = {}
            for key, field in self.skill_coefficient_fields.items():
                try:
                    coefficients[key] = float(field.value or 0)
                except (TypeError, ValueError):
                    coefficients[key] = 0.0
            self.system_data["skill_coefficients"] = coefficients

    def _calculate_auto_contributions(self):
        result = {key: 0.0 for key in STAT_LABELS}
        for slot, data in self.equipment_data.items():
            for name, value in data.get("primary", {}).items():
                key = DISPLAY_STAT_TO_KEY.get(name)
                if key:
                    result[key] += float(value or 0)
                elif slot == "weapon" and name == "命中":
                    result["damage"] += float(value or 0) / 3
            for item in data.get("secondary", []):
                key = DISPLAY_STAT_TO_KEY.get(item.get("name"))
                if key:
                    result[key] += float(item.get("value") or 0)
        for jade in self.system_data.get("jade", {}).values():
            for item in [jade.get("primary", {}), *jade.get("secondary", [])]:
                key = DISPLAY_STAT_TO_KEY.get(item.get("name"))
                if key:
                    result[key] += float(item.get("value") or 0)
        level = self._field_number(self.cur_fields, "main_skill") if self.cur_fields else int(self.growth_data.get("cur_main_skill", 0) or 0)
        for key, coefficient in self.system_data.get("skill_coefficients", {}).items():
            if key in result:
                result[key] += level * float(coefficient or 0)
        return result

    def _build_linked_stats_section(self):
        self.manual_adjust_fields = {}
        self.skill_coefficient_fields = {}
        manual = self.system_data.get("manual_adjustments", {})
        coefficients = self.system_data.get("skill_coefficients", {})
        auto = self._calculate_auto_contributions()

        jade_cards = []
        for side, label in (("core", "命魂基础"), ("yang", "阳玉魄"), ("yin", "阴玉魄")):
            jade = self.system_data.get("jade", {}).get(side, {})
            summary = []
            for item in [jade.get("primary", {}), *jade.get("secondary", [])]:
                if item.get("name") not in (None, "无") and item.get("value"):
                    summary.append(f"{item['name']} +{item['value']}")
            if side != "core" and jade.get("dust_level") is not None:
                summary.append(f"五色灵尘 {jade.get('dust_level', 0)}级")
            jade_cards.append(ft.Container(
                content=ft.Row([
                    ft.Column([ft.Text(label, weight=ft.FontWeight.BOLD), ft.Text(" · ".join(summary) if summary else "尚未配置", size=12, color=ft.Colors.ON_SURFACE_VARIANT)], expand=True),
                    ft.IconButton(ft.Icons.EDIT, on_click=lambda e, s=side: self._open_jade_editor(s)),
                ]), padding=12, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=10, expand=True,
            ))

        rows = []
        for key, label in STAT_LABELS.items():
            coefficient = ft.TextField(label="每级技能贡献", value=str(coefficients.get(key, "")), width=130, keyboard_type=ft.KeyboardType.NUMBER)
            adjustment = ft.TextField(label="手动校正", value=str(manual.get(key, "")), width=120, keyboard_type=ft.KeyboardType.NUMBER)
            self.skill_coefficient_fields[key] = coefficient
            self.manual_adjust_fields[key] = adjustment
            rows.append(ft.Row([
                ft.Text(label, width=70, weight=ft.FontWeight.BOLD),
                ft.Text(f"装备/玉魄/技能：{auto.get(key, 0):.1f}", width=180, color=ft.Colors.PRIMARY),
                coefficient, adjustment,
            ], spacing=10))

        calibrated = bool(self.system_data.get("calibrated"))
        self.linked_stats_container = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([ft.Text("属性联动与命魂之玉", size=18, weight=ft.FontWeight.BOLD), ft.Text("基础值 + 装备 + 玉魄 + 技能换算 + 手动校正 = 当前属性", size=12, color=ft.Colors.ON_SURFACE_VARIANT)], expand=True),
                    ft.Container(
                        ft.Text("已校准" if calibrated else "待校准", size=12),
                        padding=8,
                        border_radius=12,
                        bgcolor=ft.Colors.GREEN_100 if calibrated else ft.Colors.ERROR_CONTAINER,
                    ),
                ]),
                ft.Row(jade_cards, spacing=10),
                ft.ExpansionTile(title=ft.Text("技能贡献与手动校正"), controls=[ft.Column(rows, spacing=7)]),
                ft.Row([
                    ft.Button("以当前面板校准基础", icon=ft.Icons.TUNE, on_click=self._calibrate_base_stats),
                    ft.Button("重新计算当前属性", icon=ft.Icons.CALCULATE, on_click=self._recalculate_current_stats),
                ], spacing=10),
                ft.Text("技能对面板的影响因门派和技能不同：请为实际生效属性设置“每级贡献”。百分比、抗性、暴击、奇袭等非面板效果只记录，不强行折算。", size=11, color=ft.Colors.OUTLINE),
            ], spacing=10), padding=16, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=12,
        )
        return self.linked_stats_container

    def _open_jade_editor(self, side):
        self._capture_link_controls()
        jade = self.system_data.get("jade", {}).get(side, {})
        old_items = [jade.get("primary", {}), *jade.get("secondary", [])]
        rows = []
        attribute_choices = JADE_CORE_ATTRIBUTES if side == "core" else JADE_ATTRIBUTES
        row_count = 1 if side == "core" else 3
        for index in range(row_count):
            old = old_items[index] if index < len(old_items) else {}
            rows.append((self._dropdown("基础属性" if side == "core" else ("主属性" if index == 0 else f"附加属性 {index}"), attribute_choices, old.get("name", "无"), 220), self._number_field("数值", old.get("value", ""), 140)))
        special = ft.TextField(label="特殊属性 / 奇袭效果 / 祝符备注", value=jade.get("special", ""), multiline=True, min_lines=2)
        dust_level = self._number_field("五色灵尘等级", jade.get("dust_level", ""), 170) if side != "core" else None

        def apply(e):
            values = [{"name": name.value, "value": int(value.value) if value.value else 0} for name, value in rows]
            self.system_data.setdefault("jade", {})[side] = {
                "primary": values[0], "secondary": values[1:], "special": special.value or "",
                "dust_level": int(dust_level.value) if dust_level and dust_level.value else 0,
            }
            self._page.pop_dialog()
            old_container = self.linked_stats_container
            new_container = self._build_linked_stats_section()
            old_container.content = new_container.content
            self.linked_stats_container = old_container
            old_container.update()
            if self.system_data.get("calibrated"):
                self._apply_linked_current_stats(show_message=False)

        self._page.show_dialog(ft.AlertDialog(
            title=ft.Text({"core": "命魂基础属性", "yang": "阳玉魄", "yin": "阴玉魄"}[side]),
            content=ft.Column([
                *[ft.Row([name, value], spacing=12) for name, value in rows],
                *([dust_level, ft.Text("灵尘超过人物等级/10的部分可能按50%生效；请输入游戏面板最终显示值，联动时不再二次折算。", size=11, color=ft.Colors.OUTLINE)] if dust_level else []),
                special,
            ], width=620, height=360, spacing=10),
            actions=[ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()), ft.Button("应用", on_click=apply)],
        ))

    def _calibrate_base_stats(self, e):
        self._capture_link_controls()
        auto = self._calculate_auto_contributions()
        manual = self.system_data.get("manual_adjustments", {})
        self.system_data["base_stats"] = {
            key: self._field_number(self.cur_fields, key) - auto.get(key, 0) - manual.get(key, 0)
            for key in STAT_LABELS
        }
        self.system_data["calibrated"] = True
        self.db.save_role_growth_system(self.selected_role, self.system_data)
        self._page.show_dialog(ft.SnackBar(content=ft.Text("已用当前面板反推基础值，后续可安全联动重算")))
        self._load_role_data()

    def _recalculate_current_stats(self, e):
        self._capture_link_controls()
        if not self.system_data.get("calibrated"):
            self._page.show_dialog(ft.SnackBar(content=ft.Text("请先点击“以当前面板校准基础”，避免装备属性重复计算")))
            return
        self._apply_linked_current_stats(show_message=True)

    def _apply_linked_current_stats(self, show_message=False):
        auto = self._calculate_auto_contributions()
        base = self.system_data.get("base_stats", {})
        manual = self.system_data.get("manual_adjustments", {})
        for key in STAT_LABELS:
            value = round(float(base.get(key, 0)) + auto.get(key, 0) + float(manual.get(key, 0)))
            self.cur_fields[key].value = str(value)
            self.cur_fields[key].update()
        self._on_attribute_change()
        if show_message:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("已根据装备、玉魄、技能和手动校正更新当前属性；请保存")))

    def _refresh_equipment_grid(self):
        if not hasattr(self, "equipment_grid"):
            return
        cards = [self._equipment_slot_card(slot) for slot in EQUIPMENT_SLOTS]
        self.equipment_grid.controls = [
            ft.Text("六件装备", weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
            ft.Row(cards[:3], spacing=10),
            ft.Row(cards[3:6], spacing=10),
            ft.Text("四件灵饰", weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
            ft.Row(cards[6:8], spacing=10),
            ft.Row(cards[8:10], spacing=10),
        ]
        try:
            self.equipment_grid.update()
        except RuntimeError:
            pass

    def _equipment_slot_card(self, slot):
        label, icon, _ = EQUIPMENT_SLOTS[slot]
        data = self.equipment_data.get(slot, {})
        lines = self._equipment_summary(data, slot)
        configured = bool(data)
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(icon, color=ft.Colors.PRIMARY),
                    ft.Text(label, weight=ft.FontWeight.BOLD, expand=True),
                    ft.IconButton(ft.Icons.EDIT if configured else ft.Icons.ADD, tooltip="选择装备属性", on_click=lambda e, s=slot: self._open_equipment_editor(s)),
                ], spacing=6),
                ft.Text("\n".join(lines) if lines else "尚未选择", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=5),
            padding=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border.all(1, ft.Colors.PRIMARY_CONTAINER if configured else ft.Colors.OUTLINE_VARIANT),
            border_radius=12,
            expand=True,
        )

    def _equipment_summary(self, data, slot):
        if not data:
            return []
        lines = []
        if data.get("level"):
            lines.append(f"{data['level']}级")
        primary = [f"{name} {value}" for name, value in data.get("primary", {}).items() if value]
        if primary:
            lines.append(" · ".join(primary))
        secondary = [f"{item.get('name')} +{item.get('value')}" for item in data.get("secondary", []) if item.get("name") not in (None, "无") and item.get("value")]
        if secondary:
            lines.append(" · ".join(secondary))
        if slot in ACCESSORY_SLOTS:
            if data.get("stone_effect") not in (None, "无"):
                lines.append(f"钟灵石：{data['stone_effect']} {data.get('stone_level', 0)}级")
        else:
            if data.get("gem") not in (None, "无"):
                lines.append(f"{data['gem']} {data.get('gem_level', 0)}锻")
            effects = [data.get("special_skill"), data.get("special_effect")]
            effects = [value for value in effects if value not in (None, "无")]
            if effects:
                lines.append(" / ".join(effects))
        if data.get("legacy_note"):
            lines.append(f"旧记录：{data['legacy_note']}")
        return lines[:5]

    def _dropdown(self, label, values, current="无", width=180):
        return ft.Dropdown(label=label, value=str(current or values[0]), width=width, options=[ft.DropdownOption(str(value)) for value in values])

    def _number_field(self, label, value="", width=140):
        return ft.TextField(label=label, value=str(value or ""), width=width, input_filter=ft.NumbersOnlyInputFilter())

    def _open_equipment_editor(self, slot):
        label, _, primary_names = EQUIPMENT_SLOTS[slot]
        data = self.equipment_data.get(slot, {})
        is_accessory = slot in ACCESSORY_SLOTS
        levels = list(range(60, 161, 10)) if not is_accessory else list(range(60, 161, 20))
        level = self._dropdown("装备等级", levels, data.get("level", levels[0]))
        primary_fields = {name: self._number_field(name, data.get("primary", {}).get(name, "")) for name in primary_names}
        old_secondary = data.get("secondary", [])
        secondary_choices = (FRONT_ACCESSORY_ATTRIBUTES if slot in {"ring", "earring"} else BACK_ACCESSORY_ATTRIBUTES) if is_accessory else BONUS_ATTRIBUTES
        row_count = 3 if is_accessory else 2
        secondary_rows = []
        for index in range(row_count):
            old = old_secondary[index] if index < len(old_secondary) else {}
            secondary_rows.append((
                self._dropdown(f"附加属性 {index + 1}", secondary_choices, old.get("name", "无"), 190),
                self._number_field("数值", old.get("value", ""), 120),
            ))

        extra_controls = []
        if is_accessory:
            stone_effect = self._dropdown("钟灵石效果", ["无", "健步如飞", "锐不可当", "血气方刚", "固若金汤", "心无旁骛", "回春之术", "其他"], data.get("stone_effect", "无"), 210)
            stone_level = self._dropdown("钟灵石等级", list(range(0, 9)), data.get("stone_level", 0), 160)
            extra_controls.append(ft.Row([stone_effect, stone_level], spacing=12))
        else:
            gem_options = {
                "weapon": ["无", "太阳石", "红玛瑙"], "head": ["无", "月亮石", "太阳石", "红玛瑙"],
                "body": ["无", "月亮石", "光芒石", "翡翠石"], "belt": ["无", "光芒石", "黑宝石"],
                "shoes": ["无", "黑宝石", "神秘石"], "necklace": ["无", "舍利子"],
            }[slot]
            gem = self._dropdown("宝石", gem_options, data.get("gem", "无"), 180)
            gem_level = self._dropdown("锻数", list(range(0, 19)), data.get("gem_level", 0), 130)
            skill = self._dropdown("特技", SPECIAL_SKILLS, data.get("special_skill", "无"), 210)
            effect = self._dropdown("特效", SPECIAL_EFFECTS, data.get("special_effect", "无"), 210)
            set_effect = ft.TextField(label="套装 / 符石组合 / 其他效果", value=data.get("set_effect", ""), expand=True)
            extra_controls.extend([ft.Row([gem, gem_level, skill, effect], spacing=12), set_effect])
        note = ft.TextField(label="备注", value=data.get("note", data.get("legacy_note", "")), multiline=True, min_lines=1, max_lines=3)

        def save_equipment(e):
            result = {
                "level": int(level.value),
                "primary": {name: int(field.value) if field.value else 0 for name, field in primary_fields.items()},
                "secondary": [{"name": name.value, "value": int(value.value) if value.value else 0} for name, value in secondary_rows],
                "note": note.value or "",
            }
            if is_accessory:
                result.update({"stone_effect": stone_effect.value, "stone_level": int(stone_level.value)})
            else:
                result.update({"gem": gem.value, "gem_level": int(gem_level.value), "special_skill": skill.value, "special_effect": effect.value, "set_effect": set_effect.value or ""})
            self.equipment_data[slot] = result
            self._page.pop_dialog()
            self._refresh_equipment_grid()
            if self.system_data.get("calibrated"):
                self._apply_linked_current_stats(show_message=False)

        def remove_equipment(e):
            self.equipment_data.pop(slot, None)
            self._page.pop_dialog()
            self._refresh_equipment_grid()

        content = ft.Column([
            ft.Text("基础属性", weight=ft.FontWeight.BOLD),
            ft.Row([level, *primary_fields.values()], spacing=12, wrap=True),
            ft.Text("附加属性", weight=ft.FontWeight.BOLD),
            *[ft.Row([name, value], spacing=12) for name, value in secondary_rows],
            ft.Text("装备系统", weight=ft.FontWeight.BOLD),
            *extra_controls,
            note,
        ], width=820, height=520, scroll=ft.ScrollMode.AUTO, spacing=10)
        dialog = ft.AlertDialog(
            title=ft.Text(f"选择{label}属性"),
            content=content,
            actions=[
                ft.TextButton("移除", on_click=remove_equipment, visible=bool(data)),
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("应用", icon=ft.Icons.CHECK, on_click=save_equipment),
            ],
        )
        self._page.show_dialog(dialog)

    def _clear_all_equipment(self, e):
        def confirm(e):
            self.equipment_data = {}
            self._page.pop_dialog()
            self._refresh_equipment_grid()
        self._page.show_dialog(ft.AlertDialog(
            title=ft.Text("清空当前装备"),
            content=ft.Text("确定移除这个角色已选择的全部装备属性吗？点击底部“保存属性”后写入数据库。"),
            actions=[ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()), ft.Button("清空", on_click=confirm)],
        ))

    def _equipment_system_card(self, title, icon, description):
        return ft.Container(
            content=ft.Column([
                ft.Icon(icon, color=ft.Colors.PRIMARY),
                ft.Text(title, weight=ft.FontWeight.BOLD),
                ft.Text(description, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=5),
            padding=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=10,
            expand=True,
        )

    def _build_action_bar(self):
        return ft.Row([
            ft.Button("保存全部", icon=ft.Icons.SAVE, on_click=self._save_data),
            ft.IconButton(ft.Icons.CALCULATE, tooltip="按装备、玉魄和技能重新计算当前属性", on_click=self._recalculate_current_stats),
            ft.IconButton(ft.Icons.CLEAR_ALL, tooltip="清空目标", on_click=self._clear_target),
        ], spacing=6)

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
        
        # Preserve legacy free-text equipment notes for backward compatibility.
        equip_keys = ['equip_weapon', 'equip_head', 'equip_body', 'equip_belt', 'equip_shoes', 'equip_necklace']
        for key in equip_keys:
            data[key] = self.growth_data.get(key, "")
        
        self.db.upsert_role_growth(data)
        self.db.save_role_equipment(self.selected_role, self.equipment_data)
        self._capture_link_controls()
        self.db.save_role_growth_system(self.selected_role, self.system_data)
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
        self._on_attribute_change()
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
            self._on_attribute_change()
            self._page.pop_dialog()
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

    def cleanup(self):
        """清理页面资源"""
        pass
