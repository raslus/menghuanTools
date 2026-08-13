import asyncio
import flet as ft
import os
from core.growth_db import GrowthDB
from core.accounting_db import AccountingDB
from utils.platform_utils import get_app_data_dir


class AccountPage(ft.Column):
    def __init__(self, data_manager, page):
        super().__init__()
        self.data_manager = data_manager
        self._page = page
        self.file_picker = ft.FilePicker()
        self.selected_file_path = None
        self.file_picker = None
        self.workspace_tab_index = 0
        
        app_data_dir = get_app_data_dir()
        db_path = os.path.join(app_data_dir, "growth.db")
        self.growth_db = GrowthDB(db_path)
        self.accounting_db = AccountingDB(os.path.join(app_data_dir, "accounting.db"))

        self.expand = True
        self.spacing = 16

        self.account_count_text = ft.Text("0 个角色", color=ft.Colors.ON_SURFACE_VARIANT)

        self.search_field = ft.TextField(
            hint_text="按角色昵称或用户名搜索",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.on_search_change,
            expand=True,
        )

        self.add_button = ft.Button(
            "添加角色",
            icon=ft.Icons.ADD,
            on_click=self.show_add_dialog,
        )

        self.accounts_list = ft.ListView(spacing=10)

        self.empty_state = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.PERSON_ADD_ALT_1, size=64, color=ft.Colors.PRIMARY),
                    ft.Text("还没有保存账号", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("添加第一个账号，之后可以快速复制登录信息", color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Button("添加第一个账号", icon=ft.Icons.ADD, on_click=self.show_add_dialog),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment(0, 0),
        )

        self._build_ui()

    def _build_ui(self):
        self.account_toolbar = ft.Row(
            [self.search_field, self.add_button],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self.account_view = ft.Column([
            self.account_toolbar,
            self.account_count_text,
            ft.Container(
                content=ft.Stack([self.empty_state, self.accounts_list]),
                expand=True,
            ),
        ], spacing=12, expand=True)
        self.backup_view = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.SECURITY, size=44, color=ft.Colors.PRIMARY),
                    ft.Text("数据备份与迁移", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text("将账号加密导出到本地，或从已有备份恢复账号。", color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Row([
                        ft.Button("导入备份", icon=ft.Icons.UPLOAD, on_click=self.show_import_dialog),
                        ft.Button("导出备份", icon=ft.Icons.DOWNLOAD, on_click=self.show_export_dialog),
                    ], spacing=12),
                    ft.Text("建议为导出文件设置密码，并将备份保存在安全位置。", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14),
                alignment=ft.Alignment(0, -0.5),
                expand=True,
            ),
        ], expand=True)
        self.workspace_tabs_row = ft.Row(spacing=8)
        self.workspace = ft.Stack([self.account_view, self.backup_view], expand=True)
        self._build_workspace_tabs()

        self.controls = [
            ft.Column(
                [
                    ft.Text("账号管理", size=26, weight=ft.FontWeight.BOLD),
                    ft.Text("集中保管账号信息，支持加密导入和导出备份。", color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                spacing=2,
            ),
            self.workspace_tabs_row,
            self.workspace,
        ]
        self._load_accounts()
        
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_workspace_tabs(self):
        tabs = [("账号列表", ft.Icons.PEOPLE), ("数据备份", ft.Icons.BACKUP)]
        self.workspace_tabs_row.controls = [
            ft.Button(label, icon=icon, on_click=lambda e, index=i: self._switch_workspace_tab(index),
                      bgcolor=ft.Colors.PRIMARY_CONTAINER if i == self.workspace_tab_index else None)
            for i, (label, icon) in enumerate(tabs)
        ]
        self.account_view.visible = self.workspace_tab_index == 0
        self.backup_view.visible = self.workspace_tab_index == 1

    def _switch_workspace_tab(self, index):
        self.workspace_tab_index = index
        self._build_workspace_tabs()
        self.update()

    def on_search_change(self, e):
        self.refresh_accounts(e.control.value)

    def _load_accounts(self):
        self.accounts_list.controls.clear()
        accounts = self.data_manager.get_all_accounts()
        self.account_count_text.value = f"{len(accounts)} 个角色"
        if not accounts:
            self.empty_state.visible = True
            self.accounts_list.visible = False
        else:
            self.empty_state.visible = False
            self.accounts_list.visible = True
            for account in accounts:
                self.accounts_list.controls.append(self.create_account_card(account))

    def refresh_accounts(self, search_text=""):
        self.accounts_list.controls.clear()
        accounts = self.data_manager.get_all_accounts()
        if search_text:
            query = search_text.casefold()
            accounts = [a for a in accounts if query in self.data_manager.get_role_name(a).casefold()
                        or query in a.get("username", "").casefold()]
        self.account_count_text.value = f"找到 {len(accounts)} 个角色" if search_text else f"{len(accounts)} 个角色"
        if not accounts:
            empty_title = "没有匹配的账号" if search_text else "还没有保存账号"
            empty_hint = "换个关键词试试" if search_text else "添加第一个账号，之后可以快速复制登录信息"
            self.empty_state.content.controls[1].value = empty_title
            self.empty_state.content.controls[2].value = empty_hint
            self.empty_state.content.controls[3].visible = not bool(search_text)
            self.empty_state.visible = True
            self.accounts_list.visible = False
        else:
            self.empty_state.visible = False
            self.accounts_list.visible = True
            for account in accounts:
                self.accounts_list.controls.append(self.create_account_card(account))
        try:
            self._page.update()
        except RuntimeError:
            pass

    def create_account_card(self, account):
        has_password = bool(account.get("password"))

        async def do_copy(text: str, message: str):
            await ft.Clipboard().set(text)
            self.show_snackbar(message)

        def copy_username(e):
            asyncio.create_task(do_copy(account.get("username", ""), "用户名已复制"))

        def copy_password(e):
            asyncio.create_task(do_copy(account.get("password", ""), "密码已复制"))

        def edit_click(e):
            self.show_edit_dialog(account)

        def delete_click(e):
            self.show_delete_dialog(account)

        return ft.Card(
            elevation=0,
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=40),
                            title=ft.Text(self.data_manager.get_role_name(account)),
                            subtitle=ft.Text(" · ".join(filter(None, [
                                f"账号：{account.get('username')}" if account.get("username") else "未填写登录账号",
                                account.get("remark", ""),
                            ]))),
                        ),
                        ft.Row(
                            [
                                ft.TextButton("复制账号" if account.get("username") else "未设置账号",
                                              icon=ft.Icons.COPY, on_click=copy_username if account.get("username") else None,
                                              disabled=not bool(account.get("username"))),
                                ft.TextButton(
                                    "复制密码" if has_password else "未设置密码",
                                    icon=ft.Icons.COPY if has_password else ft.Icons.LOCK_OPEN,
                                    on_click=copy_password if has_password else None,
                                    disabled=not has_password,
                                ),
                                ft.Row(
                                    [
                                        ft.IconButton(
                                            icon=ft.Icons.EDIT, tooltip="编辑", on_click=edit_click,
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE, tooltip="删除",
                                            icon_color=ft.Colors.ERROR, on_click=delete_click,
                                        ),
                                    ]
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=5,
                ),
                padding=16,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=12,
            ),
        )

    def show_add_dialog(self, e):
        nickname_field = ft.TextField(label="角色昵称", autofocus=True)
        username_field = ft.TextField(label="登录账号（可选）", hint_text="可稍后补充")
        password_field = ft.TextField(
            label="密码（可选）",
            hint_text="可稍后在编辑账号时补充",
            password=True,
            can_reveal_password=True,
        )
        remark_field = ft.TextField(label="备注", multiline=True, min_lines=2, max_lines=4)

        def save_click(e):
            nickname = (nickname_field.value or "").strip()
            if not nickname:
                nickname_field.error_text = "请输入角色昵称"
                nickname_field.update()
                return
            if self.data_manager.nickname_exists(nickname):
                nickname_field.error_text = "该角色昵称已存在"
                nickname_field.update()
                return
            self.data_manager.add_account(
                nickname, username_field.value or "", password_field.value or "", remark_field.value or "",
            )
            self._page.pop_dialog()
            self.refresh_accounts()
            self.show_snackbar("角色添加成功")

        dialog = ft.AlertDialog(
            title=ft.Text("添加角色"),
            content=ft.Column([nickname_field, username_field, password_field, remark_field], tight=True),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("保存", on_click=save_click),
            ],
        )
        self._page.show_dialog(dialog)

    def show_edit_dialog(self, account):
        nickname_field = ft.TextField(label="角色昵称", value=self.data_manager.get_role_name(account))
        username_field = ft.TextField(label="登录账号（可选）", value=account.get("username", ""))
        password_field = ft.TextField(
            label="密码（可选）", value=account.get("password", ""),
            hint_text="留空表示暂不设置密码",
            password=True, can_reveal_password=True,
        )
        remark_field = ft.TextField(label="备注", value=account.get("remark", ""),
                                     multiline=True, min_lines=2, max_lines=4)

        def save_click(e):
            nickname = (nickname_field.value or "").strip()
            if not nickname:
                nickname_field.error_text = "请输入角色昵称"
                nickname_field.update()
                return
            if self.data_manager.nickname_exists(nickname, account["id"]):
                nickname_field.error_text = "该角色昵称已存在"
                nickname_field.update()
                return
            old_name = self.data_manager.get_role_name(account)
            self.data_manager.update_account(
                account["id"], nickname, username_field.value or "", password_field.value or "", remark_field.value,
            )
            if old_name != nickname:
                self.accounting_db.rename_role(old_name, nickname)
                self.growth_db.rename_role(old_name, nickname)
            self._page.pop_dialog()
            self.refresh_accounts()
            self.show_snackbar("角色信息更新成功")

        dialog = ft.AlertDialog(
            title=ft.Text("编辑角色与账号"),
            content=ft.Column([nickname_field, username_field, password_field, remark_field], tight=True),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("保存", on_click=save_click),
            ],
        )
        self._page.show_dialog(dialog)

    def show_delete_dialog(self, account):
        def confirm_delete(e):
            role_name = self.data_manager.get_role_name(account)
            self.data_manager.delete_account(account["id"])
            self.growth_db.delete_role_growth(role_name)
            deleted_income_count = self.accounting_db.delete_role_records(role_name)
            self._page.pop_dialog()
            self.refresh_accounts()
            self.show_snackbar(f"角色已删除，同时清除 {deleted_income_count} 条历史收益")

        dialog = ft.AlertDialog(
            title=ft.Text("确认删除"),
            content=ft.Text(
                f"确定要删除角色 \"{self.data_manager.get_role_name(account)}\" 吗？"
                "该角色的全部历史收益和养成数据也会被永久清除，此操作不可恢复。"
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("删除", bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR, on_click=confirm_delete),
            ],
        )
        self._page.show_dialog(dialog)

    def show_snackbar(self, message):
        self._page.show_dialog(ft.SnackBar(content=ft.Text(message)))

    def show_import_dialog(self, e):
        self.selected_file_path = None

        password_field = ft.TextField(
            label="导入密码（如有）", password=True,
            hint_text="如果导出时设置了密码，请输入",
        )
        merge_switch = ft.Switch(label="合并到现有数据", value=True)
        selected_path_text = ft.Text("未选择文件", size=12, color=ft.Colors.OUTLINE)

        async def pick_file_click(e):
            files = await self.file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["txt", "json", "bak", "enc"],
                file_type=ft.FilePickerFileType.CUSTOM,
            )
            if files:
                self.selected_file_path = files[0].path
                selected_path_text.value = f"已选择: {files[0].name}"
                selected_path_text.update()

        def do_import(e):
            if not self.selected_file_path:
                self.show_snackbar("请先选择文件")
                return
            success, count = self.data_manager.import_from_file(
                self.selected_file_path, password_field.value, merge_switch.value
            )
            if success:
                self.refresh_accounts()
                self.show_snackbar(f"成功导入 {count} 个账号")
                self._page.pop_dialog()
            else:
                self.show_snackbar("导入失败，请检查文件和密码")

        dialog = ft.AlertDialog(
            title=ft.Text("导入账号"),
            content=ft.Column(
                [
                    ft.Button("选择文件", icon=ft.Icons.FOLDER_OPEN, on_click=pick_file_click),
                    selected_path_text,
                    password_field,
                    merge_switch,
                ],
                tight=True, spacing=15,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("导入", on_click=do_import),
            ],
        )
        self._page.show_dialog(dialog)

    def show_export_dialog(self, e):
        self.selected_file_path = None

        password_field = ft.TextField(
            label="导出密码（可选）", password=True,
            hint_text="设置密码以加密导出文件",
        )
        selected_path_text = ft.Text("未选择保存位置", size=12, color=ft.Colors.OUTLINE)

        async def pick_save_click(e):
            path = await self.file_picker.save_file(
                dialog_title="导出账号备份",
                file_name="accounts_backup.txt",
                allowed_extensions=["txt"],
                file_type=ft.FilePickerFileType.CUSTOM,
            )
            if path:
                self.selected_file_path = path
                selected_path_text.value = f"保存到: {path}"
                selected_path_text.update()

        def do_export(e):
            if not self.selected_file_path:
                self.show_snackbar("请先选择保存位置")
                return
            success = self.data_manager.export_to_file(self.selected_file_path, password_field.value)
            if success:
                self.show_snackbar("导出成功")
                self._page.pop_dialog()
            else:
                self.show_snackbar("导出失败")

        dialog = ft.AlertDialog(
            title=ft.Text("导出账号"),
            content=ft.Column(
                [
                    ft.Button("选择保存位置", icon=ft.Icons.SAVE, on_click=pick_save_click),
                    selected_path_text,
                    password_field,
                ],
                tight=True, spacing=15,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._page.pop_dialog()),
                ft.Button("导出", on_click=do_export),
            ],
        )
        self._page.show_dialog(dialog)

    def cleanup(self):
        """清理页面资源"""
        pass
