import flet as ft
import matplotlib.pyplot as plt
import io
import base64
import os
from datetime import datetime, timedelta
from core.accounting_db import AccountingDB, ACTIVITY_TYPES, format_number
from utils.platform_utils import get_app_data_dir


class AccountingPage(ft.Column):
    def __init__(self, data_manager, page):
        super().__init__()
        self.data_manager = data_manager
        self._page = page
        
        app_data_dir = get_app_data_dir()
        db_path = os.path.join(app_data_dir, "accounting.db")
        self.db = AccountingDB(db_path)
        
        self.expand = True
        self.spacing = 10

        self.sort_column = "record_date"
        self.sort_asc = False

        self.start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        self.end_date = datetime.now().strftime('%Y-%m-%d')
        self.selected_role = "全部角色"
        self.selected_activity = "全部"

        self.records = []
        self.filtered_records = []
        self.workspace_tab_index = 0
        self.summary_tab_index = 0

        self._build_ui()
        self.refresh_view()

    def did_mount(self):
        """控件挂载到页面后加载数据"""
        self.refresh_view()

    def _build_ui(self):
        self.stats_grid = ft.GridView(runs_count=4, spacing=10, height=96)
        self.filter_container = ft.Container()
        self.charts_container = ft.Column(spacing=10, expand=True, scroll=ft.ScrollMode.AUTO)
        self.action_bar = ft.Row(spacing=10)
        self.table_container = ft.Container(expand=True)
        
        self.summary_container = ft.Container(expand=True)
        self.summary_tabs_row = ft.Row(spacing=5)

        self.detail_view = ft.Column(
            [self.action_bar, self.table_container],
            spacing=10,
            expand=True,
        )
        self.analysis_view = ft.Column(
            [self.stats_grid, self.charts_container],
            spacing=12,
            expand=True,
        )
        self.summary_view = ft.Column(
            [self.summary_tabs_row, self.summary_container],
            spacing=10,
            expand=True,
        )

        self.workspace_tabs_row = ft.Row(spacing=8)
        self.workspace_container = ft.Stack(
            [self.detail_view, self.analysis_view, self.summary_view],
            expand=True,
        )
        self._build_workspace_tabs()

        self.controls = [
            ft.Column([
                ft.Text("收益记账", size=26, weight=ft.FontWeight.BOLD),
                ft.Text("记录每次活动的投入与收益，快速了解角色和活动表现。", color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=2),
            ft.Container(
                content=ft.Column([
                    ft.Text("筛选记录", size=16, weight=ft.FontWeight.BOLD),
                    self.filter_container,
                ], spacing=10),
                padding=16,
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                border_radius=12,
            ),
            self.workspace_tabs_row,
            self.workspace_container,
        ]

    def _build_workspace_tabs(self):
        tab_data = [
            ("明细记录", ft.Icons.RECEIPT_LONG),
            ("数据分析", ft.Icons.INSIGHTS),
            ("分类汇总", ft.Icons.TABLE_CHART),
        ]
        self.workspace_tabs_row.controls = [
            ft.Button(
                label,
                icon=icon,
                on_click=lambda e, index=i: self._switch_workspace_tab(index),
                bgcolor=ft.Colors.PRIMARY_CONTAINER if i == self.workspace_tab_index else None,
                color=ft.Colors.ON_PRIMARY_CONTAINER if i == self.workspace_tab_index else None,
            )
            for i, (label, icon) in enumerate(tab_data)
        ]
        views = [self.detail_view, self.analysis_view, self.summary_view]
        for index, view in enumerate(views):
            view.visible = index == self.workspace_tab_index

    def _switch_workspace_tab(self, index):
        self.workspace_tab_index = index
        self._build_workspace_tabs()
        self.update()

    def _build_stats_cards(self):
        cards = []
        
        total_net = sum(r['net_profit'] for r in self.filtered_records)
        total_net_str = format_number(total_net)
        
        days = len(set(r['record_date'] for r in self.filtered_records))
        
        avg_daily = total_net / days if days > 0 else 0
        avg_daily_str = format_number(avg_daily) if days > 0 else "--"
        
        role_summary = self.db.get_role_summary(self.filtered_records)
        mvp_role = ""
        if role_summary:
            mvp_role = f"{role_summary[0]['role_name']} ({format_number(role_summary[0]['total_net'])})"
        else:
            mvp_role = "--"

        card_data = [
            {"title": "总净收益", "value": total_net_str, "icon": ft.Icons.TRENDING_UP, "color": ft.Colors.GREEN},
            {"title": "记账天数", "value": str(days), "icon": ft.Icons.CALENDAR_MONTH, "color": ft.Colors.BLUE},
            {"title": "日均净收益", "value": avg_daily_str, "icon": ft.Icons.SCHEDULE, "color": ft.Colors.ORANGE},
            {"title": "MVP角色", "value": mvp_role, "icon": ft.Icons.STAR, "color": ft.Colors.PURPLE},
        ]

        self.stats_grid.runs_count = 4

        for data in card_data:
            card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(data["icon"], color=data["color"], size=20),
                            ft.Text(data["title"], size=11, color=ft.Colors.GREY),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(data["value"], size=16, weight=ft.FontWeight.BOLD),
                    ], spacing=6),
                    padding=12,
                ),
            )
            cards.append(card)

        self.stats_grid.controls = cards

    def _build_filter_bar(self):
        role_options = ["全部角色"] + self.db.get_distinct_roles()
        activity_options = ["全部"] + ACTIVITY_TYPES

        self.date_picker_start = ft.TextField(
            label="开始日期", value=self.start_date, width=120,
            on_change=lambda e: self._on_date_change("start", e)
        )
        self.date_picker_end = ft.TextField(
            label="结束日期", value=self.end_date, width=120,
            on_change=lambda e: self._on_date_change("end", e)
        )
        
        self.role_dropdown = ft.Dropdown(
            label="角色", options=[ft.DropdownOption(r) for r in role_options],
            value=self.selected_role, width=120,
            on_select=lambda e: self._on_filter_change("role", e)
        )
        
        self.activity_dropdown = ft.Dropdown(
            label="活动", options=[ft.DropdownOption(a) for a in activity_options],
            value=self.selected_activity, width=120,
            on_select=lambda e: self._on_filter_change("activity", e)
        )

        today_btn = ft.Button("今天", on_click=self._quick_date_today, height=36)
        week_btn = ft.Button("本周", on_click=self._quick_date_week, height=36)
        month_btn = ft.Button("本月", on_click=self._quick_date_month, height=36)
        reset_btn = ft.Button("重置", on_click=self._reset_filters, height=36)

        self.filter_container.content = ft.Row([
            ft.Row([today_btn, week_btn, month_btn], spacing=5),
            ft.VerticalDivider(width=1),
            self.date_picker_start,
            ft.Text("至"),
            self.date_picker_end,
            ft.VerticalDivider(width=1),
            self.role_dropdown,
            self.activity_dropdown,
            reset_btn,
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _build_charts(self):
        if len(self.filtered_records) < 2:
            self.charts_container.controls = [
                ft.Container(
                    content=ft.Text("暂无足够数据生成图表", color=ft.Colors.GREY),
                    alignment=ft.Alignment(0, 0),
                    height=100,
                )
            ]
            return

        chart1 = self._generate_daily_trend_chart()
        chart2 = self._generate_role_ranking_chart()

        self.charts_container.controls = [
            ft.Row([
                ft.Card(
                    content=ft.Container(content=chart1, padding=10),
                    expand=True,
                ),
                ft.Card(
                    content=ft.Container(content=chart2, padding=10),
                    expand=True,
                ),
            ], spacing=10, expand=True),
        ]

    def _generate_daily_trend_chart(self):
        daily_summary = self.db.get_daily_summary(self.filtered_records)
        if not daily_summary:
            return ft.Text("暂无数据")

        dates = [d['record_date'] for d in daily_summary]
        values = [d['total_net'] for d in daily_summary]

        plt.figure(figsize=(5, 3))
        plt.plot(dates, values, marker='o', color='#4CAF50', linewidth=2)
        plt.title("每日净收益趋势", fontsize=10)
        plt.xlabel("日期", fontsize=8)
        plt.ylabel("净收益(万)", fontsize=8)
        plt.xticks(rotation=45, ha='right', fontsize=6)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode()
        plt.close()

        return ft.Image(src_base64=img_str, fit=ft.BoxFit.CONTAIN)

    def _generate_role_ranking_chart(self):
        role_summary = self.db.get_role_summary(self.filtered_records)
        if not role_summary:
            return ft.Text("暂无数据")

        roles = [r['role_name'] for r in role_summary]
        values = [r['total_net'] for r in role_summary]

        colors = ['#FFD700' if i == 0 else '#2196F3' for i in range(len(roles))]

        plt.figure(figsize=(5, 3))
        plt.bar(roles, values, color=colors)
        plt.title("各角色总净收益排行", fontsize=10)
        plt.xlabel("角色", fontsize=8)
        plt.ylabel("净收益(万)", fontsize=8)
        plt.xticks(rotation=45, ha='right', fontsize=6)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode()
        plt.close()

        return ft.Image(src_base64=img_str, fit=ft.BoxFit.CONTAIN)

    def _build_action_bar(self):
        add_btn = ft.Button(
            "+ 添加产出", icon=ft.Icons.ADD, on_click=self.show_add_dialog
        )
        copy_btn = ft.Button(
            "复制昨日记录", icon=ft.Icons.COPY, on_click=self.show_copy_dialog
        )
        export_btn = ft.Button(
            "导出 CSV", icon=ft.Icons.DOWNLOAD, on_click=self.export_csv
        )

        self.action_bar.controls = [add_btn, copy_btn, export_btn]

    def _build_data_table(self):
        # Windows desktop application: always show the complete data table.
        is_mobile = False
        
        if is_mobile:
            columns = [
                ft.DataColumn(ft.Text("日期"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("角色"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("活动"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("净收益(万)"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("操作")),
            ]
            
            rows = []
            for record in self.filtered_records:
                edit_btn = ft.IconButton(
                    icon=ft.Icons.EDIT, on_click=lambda e, r=record: self.show_edit_dialog(r),
                    icon_size=18
                )
                delete_btn = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE, on_click=lambda e, r=record: self.show_delete_dialog(r),
                    icon_color=ft.Colors.ERROR,
                    icon_size=18
                )

                row = ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(record['record_date'])),
                        ft.DataCell(ft.Text(record['role_name'])),
                        ft.DataCell(ft.Text(record['activity_type'])),
                        ft.DataCell(ft.Text(f"{record['net_profit']:.2f}")),
                        ft.DataCell(ft.Row([edit_btn, delete_btn])),
                    ]
                )
                rows.append(row)

            if not rows:
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text("暂无记录")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                ]))
        else:
            columns = [
                ft.DataColumn(ft.Text("日期"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("角色"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("活动"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("现金(万)"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("物品(万)"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("成本(万)"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("净收益(万)"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("备注"), on_sort=self._on_sort),
                ft.DataColumn(ft.Text("操作")),
            ]

            rows = []
            for record in self.filtered_records:
                edit_btn = ft.IconButton(
                    icon=ft.Icons.EDIT, on_click=lambda e, r=record: self.show_edit_dialog(r)
                )
                delete_btn = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE, on_click=lambda e, r=record: self.show_delete_dialog(r),
                    icon_color=ft.Colors.ERROR
                )

                row = ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(record['record_date'])),
                        ft.DataCell(ft.Text(record['role_name'])),
                        ft.DataCell(ft.Text(record['activity_type'])),
                        ft.DataCell(ft.Text(f"{record['cash_income']:.2f}")),
                        ft.DataCell(ft.Text(f"{record['item_income']:.2f}")),
                        ft.DataCell(ft.Text(f"{record['cost']:.2f}")),
                        ft.DataCell(ft.Text(f"{record['net_profit']:.2f}")),
                        ft.DataCell(ft.Text(record['remark'] or "")),
                        ft.DataCell(ft.Row([edit_btn, delete_btn])),
                    ]
                )
                rows.append(row)

            if not rows:
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text("暂无记录")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                    ft.DataCell(ft.Text("")),
                ]))

        self.table_container.content = ft.Column(
            controls=[ft.Row(
                controls=[ft.DataTable(columns=columns, rows=rows)],
                scroll=ft.ScrollMode.AUTO,
            )],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _build_summary_tabs(self):
        def switch_tab(index):
            self.summary_tab_index = index
            self._build_summary_tabs()
            self._update_summary_content()
            self.update()
        
        self.summary_tabs_row.controls = [
            ft.Button("按日期", icon=ft.Icons.CALENDAR_MONTH, on_click=lambda e: switch_tab(0),
                      bgcolor=ft.Colors.SECONDARY_CONTAINER if self.summary_tab_index == 0 else None),
            ft.Button("按角色", icon=ft.Icons.PERSON, on_click=lambda e: switch_tab(1),
                      bgcolor=ft.Colors.SECONDARY_CONTAINER if self.summary_tab_index == 1 else None),
            ft.Button("按活动", icon=ft.Icons.CATEGORY, on_click=lambda e: switch_tab(2),
                      bgcolor=ft.Colors.SECONDARY_CONTAINER if self.summary_tab_index == 2 else None),
        ]
        
        self._update_summary_content()
    
    def _update_summary_content(self):
        if self.summary_tab_index == 0:
            self.summary_container.content = self._build_date_summary_table()
        elif self.summary_tab_index == 1:
            self.summary_container.content = self._build_role_summary_table()
        else:
            self.summary_container.content = self._build_activity_summary_table()

    def _build_date_summary_table(self):
        daily_summary = self.db.get_daily_summary(self.filtered_records)
        
        columns = [
            ft.DataColumn(ft.Text("日期")),
            ft.DataColumn(ft.Text("总现金")),
            ft.DataColumn(ft.Text("总物品")),
            ft.DataColumn(ft.Text("总成本")),
            ft.DataColumn(ft.Text("总净收益")),
        ]

        rows = []
        for d in daily_summary:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(d['record_date'])),
                ft.DataCell(ft.Text(f"{d['total_cash']:.2f}")),
                ft.DataCell(ft.Text(f"{d['total_item']:.2f}")),
                ft.DataCell(ft.Text(f"{d['total_cost']:.2f}")),
                ft.DataCell(ft.Text(f"{d['total_net']:.2f}")),
            ]))

        if not rows:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("暂无数据")),
                ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
            ]))

        return ft.ListView(controls=[ft.DataTable(columns=columns, rows=rows)], expand=True)

    def _build_role_summary_table(self):
        role_summary = self.db.get_role_summary(self.filtered_records)
        
        columns = [
            ft.DataColumn(ft.Text("角色")),
            ft.DataColumn(ft.Text("参与天数")),
            ft.DataColumn(ft.Text("总净收益")),
            ft.DataColumn(ft.Text("日均收益")),
        ]

        rows = []
        for i, r in enumerate(role_summary):
            bg_color = ft.Colors.YELLOW_100 if i == 0 else None
            rows.append(ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(r['role_name'])),
                    ft.DataCell(ft.Text(str(r['days']))),
                    ft.DataCell(ft.Text(f"{r['total_net']:.2f}")),
                    ft.DataCell(ft.Text(f"{r['avg_daily']:.2f}")),
                ],
                color=ft.Colors.with_opacity(0.5, bg_color) if bg_color else None
            ))

        if not rows:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("暂无数据")),
                ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
            ]))

        return ft.ListView(controls=[ft.DataTable(columns=columns, rows=rows)], expand=True)

    def _build_activity_summary_table(self):
        activity_summary = self.db.get_activity_summary(self.filtered_records)
        
        columns = [
            ft.DataColumn(ft.Text("活动类型")),
            ft.DataColumn(ft.Text("记录次数")),
            ft.DataColumn(ft.Text("总净收益")),
            ft.DataColumn(ft.Text("平均每次收益")),
        ]

        rows = []
        for a in activity_summary:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(a['activity_type'])),
                ft.DataCell(ft.Text(str(a['count']))),
                ft.DataCell(ft.Text(f"{a['total_net']:.2f}")),
                ft.DataCell(ft.Text(f"{a['avg_per_time']:.2f}")),
            ]))

        if not rows:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text("暂无数据")),
                ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
                ft.DataCell(ft.Text("")),
            ]))

        return ft.ListView(controls=[ft.DataTable(columns=columns, rows=rows)], expand=True)

    def refresh_view(self):
        self.records = self.db.get_all_records()
        self.filtered_records = self.db.get_records_by_filter(
            self.start_date, self.end_date, self.selected_role, self.selected_activity
        )
        self._apply_sort()

        self._build_stats_cards()
        self._build_filter_bar()
        self._build_charts()
        self._build_action_bar()
        self._build_data_table()
        self._build_summary_tabs()
        self._build_workspace_tabs()

        try:
            self.update()
        except RuntimeError:
            pass

    def _apply_sort(self):
        if self.sort_column == "record_date":
            self.filtered_records.sort(key=lambda x: x[self.sort_column], reverse=not self.sort_asc)
        elif self.sort_column in ["cash_income", "item_income", "cost", "net_profit"]:
            self.filtered_records.sort(key=lambda x: float(x[self.sort_column]), reverse=not self.sort_asc)
        else:
            self.filtered_records.sort(key=lambda x: str(x[self.sort_column]), reverse=not self.sort_asc)

    def _on_sort(self, e):
        if e.column_index == 0:
            self.sort_column = "record_date"
        elif e.column_index == 1:
            self.sort_column = "role_name"
        elif e.column_index == 2:
            self.sort_column = "activity_type"
        elif e.column_index == 3:
            self.sort_column = "cash_income"
        elif e.column_index == 4:
            self.sort_column = "item_income"
        elif e.column_index == 5:
            self.sort_column = "cost"
        elif e.column_index == 6:
            self.sort_column = "net_profit"
        elif e.column_index == 7:
            self.sort_column = "remark"

        self.sort_asc = not self.sort_asc
        self.refresh_view()

    def _on_date_change(self, date_type, e):
        if date_type == "start":
            self.start_date = e.control.value
        else:
            self.end_date = e.control.value
        self.refresh_view()

    def _on_filter_change(self, filter_type, e):
        if filter_type == "role":
            self.selected_role = e.control.value
        else:
            self.selected_activity = e.control.value
        self.refresh_view()

    def _quick_date_today(self, e):
        today = datetime.now().strftime('%Y-%m-%d')
        self.start_date = today
        self.end_date = today
        self.refresh_view()

    def _quick_date_week(self, e):
        today = datetime.now()
        start = today - timedelta(days=today.weekday())
        self.start_date = start.strftime('%Y-%m-%d')
        self.end_date = today.strftime('%Y-%m-%d')
        self.refresh_view()

    def _quick_date_month(self, e):
        today = datetime.now()
        start = today.replace(day=1)
        self.start_date = start.strftime('%Y-%m-%d')
        self.end_date = today.strftime('%Y-%m-%d')
        self.refresh_view()

    def _reset_filters(self, e):
        today = datetime.now()
        start = today.replace(day=1)
        self.start_date = start.strftime('%Y-%m-%d')
        self.end_date = today.strftime('%Y-%m-%d')
        self.selected_role = "全部角色"
        self.selected_activity = "全部"
        self.refresh_view()

    def show_add_dialog(self, e):
        accounts = self.data_manager.get_all_accounts()
        if not accounts:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("请先在【账号管理】中添加角色")))
            return

        role_options = [ft.DropdownOption(a['username']) for a in accounts]
        
        role_dropdown = ft.Dropdown(label="角色", options=role_options, width=200)
        date_field = ft.TextField(label="日期", value=datetime.now().strftime('%Y-%m-%d'), width=200)
        activity_dropdown = ft.Dropdown(label="活动类型", options=[ft.DropdownOption(a) for a in ACTIVITY_TYPES], width=200)
        cash_field = ft.TextField(label="现金收入(万)", width=200)
        item_field = ft.TextField(label="物品收入(万)", width=200)
        cost_field = ft.TextField(label="成本消耗(万)", width=200)
        remark_field = ft.TextField(label="备注", multiline=True, min_lines=2, max_lines=4)
        
        preview_text = ft.Text("预计净收益：0.00 万")

        def update_preview(e):
            try:
                cash = float(cash_field.value) if cash_field.value else 0
                item = float(item_field.value) if item_field.value else 0
                cost = float(cost_field.value) if cost_field.value else 0
                net = cash + item - cost
                preview_text.value = f"预计净收益：{net:.2f} 万"
                preview_text.update()
            except:
                preview_text.value = "预计净收益：0.00 万"
                preview_text.update()

        cash_field.on_change = update_preview
        item_field.on_change = update_preview
        cost_field.on_change = update_preview

        def save_click(e):
            role = role_dropdown.value
            date = date_field.value
            activity = activity_dropdown.value
            
            if not role:
                role_dropdown.error_text = "请选择角色"
                role_dropdown.update()
                return
            if not date:
                date_field.error_text = "请输入日期"
                date_field.update()
                return
            if not activity:
                activity_dropdown.error_text = "请选择活动类型"
                activity_dropdown.update()
                return

            try:
                cash = float(cash_field.value) if cash_field.value else 0
                item = float(item_field.value) if item_field.value else 0
                cost = float(cost_field.value) if cost_field.value else 0
                
                if cash < 0:
                    cash_field.error_text = "现金收入不能为负数"
                    cash_field.update()
                    return
                if item < 0:
                    item_field.error_text = "物品收入不能为负数"
                    item_field.update()
                    return
                if cost < 0:
                    cost_field.error_text = "成本消耗不能为负数"
                    cost_field.update()
                    return

                net_profit = cash + item - cost
                self.db.insert_record(role, date, activity, cash, item, cost, net_profit, remark_field.value)
                self._page.pop_dialog()
                self.refresh_view()
                self._page.show_dialog(ft.SnackBar(content=ft.Text("记录添加成功")))
            except ValueError:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请输入有效的数字")))

        dialog = ft.AlertDialog(
            title=ft.Text("添加产出记录"),
            content=ft.Column([
                role_dropdown,
                date_field,
                activity_dropdown,
                cash_field,
                item_field,
                cost_field,
                remark_field,
                preview_text,
            ], tight=True, spacing=10),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("保存", on_click=save_click),
            ],
        )
        self._page.show_dialog(dialog)

    def show_edit_dialog(self, record):
        accounts = self.data_manager.get_all_accounts()
        role_options = [ft.DropdownOption(a['username']) for a in accounts]
        
        role_dropdown = ft.Dropdown(label="角色", options=role_options, value=record['role_name'], width=200)
        date_field = ft.TextField(label="日期", value=record['record_date'], width=200)
        activity_dropdown = ft.Dropdown(label="活动类型", options=[ft.DropdownOption(a) for a in ACTIVITY_TYPES], value=record['activity_type'], width=200)
        cash_field = ft.TextField(label="现金收入(万)", value=str(record['cash_income']), width=200)
        item_field = ft.TextField(label="物品收入(万)", value=str(record['item_income']), width=200)
        cost_field = ft.TextField(label="成本消耗(万)", value=str(record['cost']), width=200)
        remark_field = ft.TextField(label="备注", multiline=True, min_lines=2, max_lines=4, value=record['remark'] or "")
        
        preview_text = ft.Text(f"预计净收益：{record['net_profit']:.2f} 万")

        def update_preview(e):
            try:
                cash = float(cash_field.value) if cash_field.value else 0
                item = float(item_field.value) if item_field.value else 0
                cost = float(cost_field.value) if cost_field.value else 0
                net = cash + item - cost
                preview_text.value = f"预计净收益：{net:.2f} 万"
                preview_text.update()
            except:
                preview_text.value = "预计净收益：0.00 万"
                preview_text.update()

        cash_field.on_change = update_preview
        item_field.on_change = update_preview
        cost_field.on_change = update_preview

        def save_click(e):
            role = role_dropdown.value
            date = date_field.value
            activity = activity_dropdown.value
            
            if not role:
                role_dropdown.error_text = "请选择角色"
                role_dropdown.update()
                return
            if not date:
                date_field.error_text = "请输入日期"
                date_field.update()
                return

            try:
                cash = float(cash_field.value) if cash_field.value else 0
                item = float(item_field.value) if item_field.value else 0
                cost = float(cost_field.value) if cost_field.value else 0
                
                if cash < 0:
                    cash_field.error_text = "现金收入不能为负数"
                    cash_field.update()
                    return
                if item < 0:
                    item_field.error_text = "物品收入不能为负数"
                    item_field.update()
                    return
                if cost < 0:
                    cost_field.error_text = "成本消耗不能为负数"
                    cost_field.update()
                    return

                net_profit = cash + item - cost
                self.db.update_record(record['id'], role, date, activity, cash, item, cost, net_profit, remark_field.value)
                self._page.pop_dialog()
                self.refresh_view()
                self._page.show_dialog(ft.SnackBar(content=ft.Text("记录更新成功")))
            except ValueError:
                self._page.show_dialog(ft.SnackBar(content=ft.Text("请输入有效的数字")))

        dialog = ft.AlertDialog(
            title=ft.Text("编辑产出记录"),
            content=ft.Column([
                role_dropdown,
                date_field,
                activity_dropdown,
                cash_field,
                item_field,
                cost_field,
                remark_field,
                preview_text,
            ], tight=True, spacing=10),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("保存", on_click=save_click),
            ],
        )
        self._page.show_dialog(dialog)

    def show_delete_dialog(self, record):
        def confirm_delete(e):
            self.db.delete_record(record['id'])
            self._page.pop_dialog()
            self.refresh_view()
            self._page.show_dialog(ft.SnackBar(content=ft.Text("记录删除成功")))

        dialog = ft.AlertDialog(
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定要删除日期 {record['record_date']}、角色 {record['role_name']} 的记录吗？"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("删除", bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR, on_click=confirm_delete),
            ],
        )
        self._page.show_dialog(dialog)

    def show_copy_dialog(self, e):
        yesterday_records = self.db.get_yesterday_records()
        
        if not yesterday_records:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("昨日无记录可复制")))
            return

        def confirm_copy(e):
            today = datetime.now().strftime('%Y-%m-%d')
            for record in yesterday_records:
                self.db.insert_record(
                    record['role_name'],
                    today,
                    record['activity_type'],
                    record['cash_income'],
                    record['item_income'],
                    record['cost'],
                    record['net_profit'],
                    record['remark'],
                )
            self._page.pop_dialog()
            self.refresh_view()
            self._page.show_dialog(ft.SnackBar(content=ft.Text(f"成功复制 {len(yesterday_records)} 条记录")))

        dialog = ft.AlertDialog(
            title=ft.Text("复制昨日记录"),
            content=ft.Text(f"检测到昨日有 {len(yesterday_records)} 条记录，确认复制到今天吗？"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("确认复制", on_click=confirm_copy),
            ],
        )
        self._page.show_dialog(dialog)

    def export_csv(self, e):
        if not self.filtered_records:
            self._page.show_dialog(ft.SnackBar(content=ft.Text("暂无数据可导出")))
            return

        csv_content = "日期,角色,活动,现金收入(万),物品收入(万),成本(万),净收益(万),备注\n"
        for record in self.filtered_records:
            csv_content += f"{record['record_date']},{record['role_name']},{record['activity_type']},{record['cash_income']},{record['item_income']},{record['cost']},{record['net_profit']},\"{record['remark'] or ''}\"\n"
        
        app_data_dir = get_app_data_dir()
        filepath = os.path.join(app_data_dir, "accounting_export.csv")
        
        with open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(csv_content)
        
        self._page.show_dialog(ft.SnackBar(content=ft.Text(f"导出成功！文件已保存到 {filepath}")))

    def cleanup(self):
        """清理页面资源"""
        pass
