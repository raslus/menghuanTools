import flet as ft
from pages.account_page import AccountPage
from pages.stats_page import StatsPage
from data_manager import DataManager


def main(page: ft.Page):
    page.title = "账号管理系统"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.padding = 0
    page.window.width = 900
    page.window.height = 600

    data_manager = DataManager()

    # 内容区域
    content_area = ft.Container(expand=True, padding=20)

    def switch_page(index: int):
        """切换页面"""
        rail.selected_index = index
        if index == 0:
            content_area.content = AccountPage(data_manager, page)
        else:
            content_area.content = StatsPage()
        page.update()

    # 导航栏
    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        min_extended_width=200,
        group_alignment=-0.9,
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.PEOPLE_OUTLINE,
                selected_icon=ft.Icons.PEOPLE,
                label="账号管理",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.ANALYTICS_OUTLINED,
                selected_icon=ft.Icons.ANALYTICS,
                label="统计页面",
            ),
        ],
        on_change=lambda e: switch_page(e.control.selected_index),
    )

    # 主布局
    page.add(
        ft.Column(
            [
                ft.AppBar(
                    title=ft.Text("账号管理系统"),
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                ),
                ft.Row(
                    [
                        rail,
                        ft.VerticalDivider(width=1),
                        content_area,
                    ],
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        )
    )

    # 初始化第一个页面
    switch_page(0)


ft.run(main)
