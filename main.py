import os

import flet as ft
from pages.account_page import AccountPage
from pages.accounting_page import AccountingPage
from pages.growth_page import GrowthPage
from pages.ghost_hunter_page import GhostHunterPage
from data_manager import DataManager
from platform_utils import get_app_data_dir


def main(page: ft.Page):
    page.title = "账号管理系统"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.padding = 0

    app_data_dir = get_app_data_dir()
    accounts_file = os.path.join(app_data_dir, "accounts.json")
    data_manager = DataManager(data_file=accounts_file)

    content_container = ft.Container(expand=True, padding=10)

    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=80,
        min_extended_width=160,
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.PEOPLE_OUTLINE,
                selected_icon=ft.Icons.PEOPLE,
                label="账号管理",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.BOOKMARKS_OUTLINED,
                selected_icon=ft.Icons.BOOKMARKS,
                label="记账本",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.TRENDING_UP_OUTLINED,
                selected_icon=ft.Icons.TRENDING_UP,
                label="养成规划",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.STAR_OUTLINED,
                selected_icon=ft.Icons.STAR,
                label="抓鬼辅助",
            ),
        ],
    )

    page.add(
        ft.Column(
            [
                ft.AppBar(title=ft.Text("账号管理系统"), bgcolor=ft.Colors.PRIMARY_CONTAINER),
                ft.Row(
                    [
                        nav_rail,
                        ft.VerticalDivider(width=1),
                        content_container,
                    ],
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        )
    )

    def switch_page(index: int):
        nav_rail.selected_index = index
        if index == 0:
            content_container.content = AccountPage(data_manager, page)
        elif index == 1:
            content_container.content = AccountingPage(data_manager, page)
        elif index == 2:
            content_container.content = GrowthPage(data_manager, page)
        else:
            content_container.content = GhostHunterPage(data_manager, page)
        page.update()

    nav_rail.on_change = lambda e: switch_page(e.control.selected_index)
    switch_page(0)


ft.run(main)