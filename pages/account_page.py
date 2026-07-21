import asyncio
import flet as ft


class AccountPage(ft.Column):
    def __init__(self, data_manager, flet_page):
        super().__init__()
        self.data_manager = data_manager
        self.flet_page = flet_page
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
                [self.search_field, self.add_button],
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
