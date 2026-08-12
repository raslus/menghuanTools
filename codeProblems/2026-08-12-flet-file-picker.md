# Flet FilePicker 初始化错误

## 问题

点击“选择地图图片”时出现：

`FilePicker.__init__() got an unexpected keyword argument 'on_result'`

## 原因

项目使用 Flet 0.86.2。该版本的 `FilePicker` 是自动注册的 Service：构造函数不再接受 `on_result`，同时 `Page` 也不提供 `pick_files` 或 `save_file`。

## 解决

- 页面持有 `FilePicker()` Service 实例。
- 使用 `await file_picker.pick_files(...)`，其返回值直接是文件列表。
- 使用 `await file_picker.save_file(...)` 获取保存路径。
- 自定义扩展名过滤显式设置 `FilePickerFileType.CUSTOM`。
- 同步修复账号导入与导出中的同类 Page API 调用。
