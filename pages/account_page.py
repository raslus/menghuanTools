import asyncio
import flet as ft


class AccountPage(ft.Column):
    def __init__(self, data_manager, flet_page, file_picker):
        super().__init__()
        self.data_manager = data_manager
        self.flet_page = flet_page
        self.file_picker = file_picker
        self.selected_file_path = None
        self.expand = True
        self.spacing = 10

        # 搜索框
        self.search_field = ft.TextField(
            label="搜索账号",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.on_search_change,
            expand=True,
        )

        # 添加按钮
        self.add_button = ft.ElevatedButton(
            "添加账号",
            icon=ft.Icons.ADD,
            on_click=self.show_add_dialog,
        )

        # 导入导出按钮
        self.import_button = ft.IconButton(
            icon=ft.Icons.UPLOAD,
            tooltip="导入账号",
            on_click=self.show_import_dialog,
        )
        self.export_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD,
            tooltip="导出账号",
            on_click=self.show_export_dialog,
        )

        # 账号列表 - 使用 ListView 代替 Column 以获得更好的滚动性能
        self.accounts_list = ft.ListView(expand=True, spacing=10)

        # 空状态提示
        self.empty_state = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.INBOX, size=64, color=ft.Colors.OUTLINE),
                    ft.Text("暂无账号数据", size=16, color=ft.Colors.OUTLINE),
                    ft.Text("点击右上角按钮添加账号", size=12, color=ft.Colors.OUTLINE),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment(0, 0),  # center center
            expand=True,
        )

        self.controls = [
            ft.Row(
                [
                    self.search_field,
                    ft.Row(
                        [self.import_button, self.export_button, self.add_button],
                        spacing=10,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Divider(),
            ft.Stack([self.empty_state, self.accounts_list], expand=True),
        ]

    def did_mount(self):
        """控件挂载到页面后加载数据"""
        self.refresh_accounts()

    def refresh_accounts(self, search_text=""):
        """刷新账号列表"""
        self.accounts_list.controls.clear()
        accounts = self.data_manager.get_all_accounts()

        if search_text:
            accounts = [a for a in accounts if search_text.lower() in a.get("username", "").lower()]

        if not accounts:
            self.empty_state.visible = True
            self.accounts_list.visible = False
        else:
            self.empty_state.visible = False
            self.accounts_list.visible = True
            for account in accounts:
                self.accounts_list.controls.append(self.create_account_card(account))

        self.update()

    def create_account_card(self, account):
        """创建账号卡片"""
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
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=40),
                            title=ft.Text(account.get("username", "")),
                            subtitle=ft.Text(account.get("remark", "") or "无备注"),
                        ),
                        ft.Row(
                            [
                                ft.TextButton("复制用户名", icon=ft.Icons.COPY, on_click=copy_username),
                                ft.TextButton("复制密码", icon=ft.Icons.COPY, on_click=copy_password),
                                ft.Row(
                                    [
                                        ft.IconButton(
                                            icon=ft.Icons.EDIT,
                                            tooltip="编辑",
                                            on_click=edit_click,
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE,
                                            tooltip="删除",
                                            icon_color=ft.Colors.ERROR,
                                            on_click=delete_click,
                                        ),
                                    ]
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=5,
                ),
                padding=15,
            ),
        )

    def show_add_dialog(self, e):
        """显示添加账号对话框"""
        username_field = ft.TextField(label="用户名", autofocus=True)
        password_field = ft.TextField(label="密码", password=True, can_reveal_password=True)
        remark_field = ft.TextField(label="备注", multiline=True, min_lines=2, max_lines=4)

        def save_click(e):
            if not username_field.value:
                username_field.error_text = "请输入用户名"
                username_field.update()
                return
            if not password_field.value:
                password_field.error_text = "请输入密码"
                password_field.update()
                return

            self.data_manager.add_account(
                username_field.value,
                password_field.value,
                remark_field.value or "",
            )
            self.page.pop_dialog()
            self.refresh_accounts()
            self.show_snackbar("账号添加成功")

        def cancel_click(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("添加账号"),
            content=ft.Column([username_field, password_field, remark_field], tight=True),
            actions=[
                ft.TextButton("取消", on_click=cancel_click),
                ft.ElevatedButton("保存", on_click=save_click),
            ],
        )

        self.page.show_dialog(dialog)

    def show_edit_dialog(self, account):
        """显示编辑账号对话框"""
        username_field = ft.TextField(label="用户名", value=account.get("username", ""))
        password_field = ft.TextField(
            label="密码",
            value=account.get("password", ""),
            password=True,
            can_reveal_password=True,
        )
        remark_field = ft.TextField(
            label="备注",
            value=account.get("remark", ""),
            multiline=True,
            min_lines=2,
            max_lines=4,
        )

        def save_click(e):
            if not username_field.value:
                username_field.error_text = "请输入用户名"
                username_field.update()
                return

            self.data_manager.update_account(
                account["id"],
                username_field.value,
                password_field.value,
                remark_field.value,
            )
            self.page.pop_dialog()
            self.refresh_accounts()
            self.show_snackbar("账号更新成功")

        def cancel_click(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("编辑账号"),
            content=ft.Column([username_field, password_field, remark_field], tight=True),
            actions=[
                ft.TextButton("取消", on_click=cancel_click),
                ft.ElevatedButton("保存", on_click=save_click),
            ],
        )

        self.page.show_dialog(dialog)

    def show_delete_dialog(self, account):
        """显示删除确认对话框"""
        def confirm_delete(e):
            self.data_manager.delete_account(account["id"])
            self.page.pop_dialog()
            self.refresh_accounts()
            self.show_snackbar("账号删除成功")

        def cancel_click(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定要删除账号 \"{account.get('username', '')}\" 吗？此操作不可恢复。"),
            actions=[
                ft.TextButton("取消", on_click=cancel_click),
                ft.ElevatedButton("删除", bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR, on_click=confirm_delete),
            ],
        )

        self.page.show_dialog(dialog)

    def on_search_change(self, e):
        """搜索框内容变化时触发"""
        self.refresh_accounts(e.control.value)

    def show_snackbar(self, message):
        """显示提示消息"""
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))

    def show_import_dialog(self, e):
        """显示导入对话框 - 使用 FilePicker 选择文件"""
        self.selected_file_path = None

        password_field = ft.TextField(
            label="导入密码（如有）",
            password=True,
            hint_text="如果导出时设置了密码，请输入",
        )
        merge_switch = ft.Switch(label="合并到现有数据", value=True)
        selected_path_text = ft.Text("未选择文件", size=12, color=ft.Colors.OUTLINE)

        def on_file_picked(e):
            if e.files and len(e.files) > 0:
                self.selected_file_path = e.files[0].path
                selected_path_text.value = f"已选择: {e.files[0].name}"
                selected_path_text.update()

        def pick_file_click(e):
            # 重置并设置新的回调
            self.file_picker.on_result = on_file_picked
            self.file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["txt", "json", "bak", "enc"],
                dialog_title="选择账号备份文件"
            )

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
                self.page.pop_dialog()
            else:
                self.show_snackbar("导入失败，请检查文件和密码")

        def close_dialog(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("导入账号"),
            content=ft.Column(
                [
                    ft.Text("选择之前导出的账号备份文件"),
                    ft.ElevatedButton(
                        "选择文件",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=pick_file_click,
                    ),
                    selected_path_text,
                    password_field,
                    merge_switch,
                    ft.Text("提示：在 Android 上会自动请求存储权限", size=11, color=ft.Colors.OUTLINE),
                ],
                tight=True,
                spacing=15,
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton("导入", on_click=do_import),
            ],
        )

        self.page.show_dialog(dialog)

    def show_export_dialog(self, e):
        """显示导出对话框 - 使用 FilePicker 选择保存路径"""
        self.selected_file_path = None

        password_field = ft.TextField(
            label="导出密码（可选）",
            password=True,
            hint_text="设置密码以加密导出文件",
        )
        selected_path_text = ft.Text("未选择保存位置", size=12, color=ft.Colors.OUTLINE)

        def on_save_picked(e):
            if e.path:
                self.selected_file_path = e.path
                selected_path_text.value = f"保存到: {e.path}"
                selected_path_text.update()

        def pick_save_click(e):
            # 重置并设置新的回调
            self.file_picker.on_result = on_save_picked
            self.file_picker.save_file(
                dialog_title="导出账号备份",
                file_name="accounts_backup.txt",
                allowed_extensions=["txt"],
            )

        def do_export(e):
            if not self.selected_file_path:
                self.show_snackbar("请先选择保存位置")
                return
            success = self.data_manager.export_to_file(
                self.selected_file_path, password_field.value
            )
            if success:
                self.show_snackbar("导出成功")
                self.page.pop_dialog()
            else:
                self.show_snackbar("导出失败")

        def close_dialog(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("导出账号"),
            content=ft.Column(
                [
                    ft.Text("选择导出文件的保存位置"),
                    ft.ElevatedButton(
                        "选择保存位置",
                        icon=ft.Icons.SAVE,
                        on_click=pick_save_click,
                    ),
                    selected_path_text,
                    password_field,
                    ft.Text("提示：设置密码可保护您的账号数据", size=11, color=ft.Colors.OUTLINE),
                    ft.Text("Android 会自动保存到 Download 目录", size=11, color=ft.Colors.OUTLINE),
                ],
                tight=True,
                spacing=15,
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton("导出", on_click=do_export),
            ],
        )

        self.page.show_dialog(dialog)
