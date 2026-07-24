import flet as ft


class StatsPage:
    def __init__(self):
        self.total_text = ft.Text("--", size=32, weight=ft.FontWeight.BOLD)
        self.recent_text = ft.Text("--", size=32, weight=ft.FontWeight.BOLD)

        self.stats_row = ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Icon(ft.Icons.PEOPLE, size=48, color=ft.Colors.PRIMARY),
                                    ft.Text("总账号数", size=14, color=ft.Colors.OUTLINE),
                                    self.total_text,
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=5,
                            ),
                            padding=20,
                        ),
                    ),
                    col={"sm": 12, "md": 6, "lg": 4},
                ),
                ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Icon(ft.Icons.TRENDING_UP, size=48, color=ft.Colors.SECONDARY),
                                    ft.Text("本周新增", size=14, color=ft.Colors.OUTLINE),
                                    self.recent_text,
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=5,
                            ),
                            padding=20,
                        ),
                    ),
                    col={"sm": 12, "md": 6, "lg": 4},
                ),
                ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=48, color=ft.Colors.TERTIARY),
                                    ft.Text("今日操作", size=14, color=ft.Colors.OUTLINE),
                                    ft.Text("预留", size=32, weight=ft.FontWeight.BOLD),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=5,
                                expand=True,
                            ),
                            padding=20,
                        ),
                    ),
                    col={"sm": 12, "md": 6, "lg": 4},
                ),
            ]
        )

        self.chart_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("数据趋势", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Icon(ft.Icons.BAR_CHART, size=64, color=ft.Colors.OUTLINE_VARIANT),
                                    ft.Text("图表功能预留区域", color=ft.Colors.OUTLINE),
                                    ft.Text("可在此处添加数据可视化图表", size=12, color=ft.Colors.OUTLINE),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            alignment=ft.Alignment.CENTER,
                            height=300,
                        ),
                    ]
                ),
                padding=20,
            ),
            expand=True,
        )

        self.activity_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("最近活动", size=18, weight=ft.FontWeight.BOLD),
                        ft.ListView(
                            [
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.INFO, color=ft.Colors.PRIMARY),
                                    title=ft.Text("系统初始化完成"),
                                    subtitle=ft.Text("预留功能区域"),
                                ),
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.CONSTRUCTION, color=ft.Colors.OUTLINE),
                                    title=ft.Text("更多统计功能开发中..."),
                                    subtitle=ft.Text("敬请期待"),
                                ),
                            ],
                            expand=True,
                        ),
                    ],
                    expand=True,
                ),
                padding=20,
                height=300,
            ),
            expand=True,
        )

    def build(self):
        return ft.Column(
            [
                ft.Text("统计概览", size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.stats_row,
                ft.ResponsiveRow(
                    [
                        ft.Container(content=self.chart_card, col={"sm": 12, "lg": 8}),
                        ft.Container(content=self.activity_card, col={"sm": 12, "lg": 4}),
                    ]
                ),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=20,
        )

    def load_stats(self):
        pass