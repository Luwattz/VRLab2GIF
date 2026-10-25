# Virtual Reality Lab 视角合成器

**1.2.4**：主题切换改为 Windows 整体画面合成，解决日志标题、按钮栏等控件分批重绘造成的横纹。大卡片使用缓存圆角切片，减少首次切页停顿；两个滑块按 60 Hz 帧预算调度，动画期间临时提高 Windows 定时精度，结束即释放。

Dark / Light 切换时，主体作为完整画面统一渐变，标题栏与顶部选择器同步配色。支持途中反向选择，默认仍为 Dark；本机 150% 缩放下动画帧间隔通常约 17 ms，性能及限制详见 [主题过渡说明](docs/theme-transition.md)。

右上角保留 ACT-WBEX-Updater 风格的分段按钮，两个标签固定显示，选中块平滑滑动，支持快速反向切换、按下取消及键盘操作，并遵循 Windows 动画设置。

从 `.OptisVR` / `.speos360` 直接生成 GIF，支持文件拖入、真实 H/V 角度标注及筛选、垂直角度分组和 PowerPoint 导出。PPT 首页展示全角度合集；版权、开发公司及默认页脚为 Intelligent Efficiency Team。

VRLab 2024 R1 的 COM 导出文件名使用索引，与手动菜单导出的角度文件名不同。本程序从已验证的源文件元数据恢复真实 H/V 角度，详见 [调查与验证](docs/observer-angles.md)。

支持导出 PowerPoint。GIF 生成成功后，点击底部“导出 PPT…”，填写标题、页脚、内容范围和保存位置。每个 GIF 一页，保留完整动画。PPT 采用 LumiDyna 的微软雅黑橙色标题、母版上下横线、页脚和自动页码，详见 [PPT 导出说明](docs/ppt-export.md)。

仅通过视角文件生成 GIF，支持拖入文件。已移除 PNG 文件夹选择与转换入口。程序自动调用本机 Ansys VRLab 打开文件、导出观察视角并生成 GIF，中间 PNG 自动清理。

[Dark 界面](docs/dark-mode.png) · [Light 界面](docs/light-mode.png) · [角度筛选页](docs/angle-filters.png) · [运行日志页](docs/runtime-logs.png)

## 使用

正式版本位于 [GitHub Releases](https://github.com/Luwattz/VRLab2GIF/releases/latest)。下载 `VRLab2GIF.exe`，或下载包含说明文档的 `VRLab2GIF-Windows-x64.zip`。本地构建输出为 `dist/1.2.4/VRLab2GIF.exe`。无需安装 Python；单独复制 EXE 即可运行，Arial 与原生拖放组件均已内嵌。

1. 从资源管理器将一个 `.OptisVR` 或 `.speos360` 视角文件拖入程序窗口，也可以点击“选择文件…”或手动填写路径。
2. 输出默认在源文件旁的 `文件名_GIF` 文件夹，可更改。自定义输出后，换输入文件会保留自定义位置。
3. 在“生成设置”页设置每帧延时（默认 300 ms）和角度字号（默认 24 px）；按需切到“角度筛选”页填写范围。
4. 点击“开始生成 GIF”。拖入只选择文件，不会自动启动转换。
5. 完成后点击“打开输出”。生成时可切到“运行日志”页查看过程，Esc 取消，Ctrl+Enter 开始。
6. 如需汇报文件，点击“导出 PPT…”，选择全部已生成 GIF 或仅合集，再导出。设置界面可查看 [Dark 预览](docs/ppt-export-dark.png) / [Light 预览](docs/ppt-export-light.png)。生成 PPTX 不要求安装 PowerPoint；动画在桌面 PowerPoint 的幻灯片放映中播放。

分页切换保留文件路径、参数、角度范围、日志和各页滚动位置。Ctrl+Tab / Ctrl+Shift+Tab 可前后切页。角度筛选标签显示“已设”或“检查”，提醒隐藏页上的筛选仍然生效；清除筛选后恢复普通标签。生成中分页仍可切换，处理失败自动显示日志页；在其他页面拖入新文件会返回生成设置页。

分页设计参考 apple-design 技能中的导航定位、分组、字体层级和即时反馈原则；该技能没有专门的分页模板，共享底座和选中块是针对本应用的具体设计。控件使用系统字体，分页和主题均采用分段滑块并保留键盘操作；切换立即响应，Dark/Light 配色及显示缩放同步适配。

需要 **Windows、本机已安装并注册的 Ansys Virtual Reality Lab，以及可用授权**。导出接口要求显示 VRLab 窗口，运行期间会短暂出现。首次验证建议使用 [官方样例](samples/ansys-vrlab/README.md)，角度筛选留空。

## 输入范围与角度标记

- 仅接收 `.OptisVR` / `.speos360` 中已有的观察视角；不接收 PNG 文件夹、PNG 单图或其他格式。
- 尚不支持沉浸式全景及 XMP、EXR、HDR、PIC。这些格式需要另行开发渲染流程。所用 [官方导出接口](https://developer.ansys.com/docs/speos-labs-automation-2024-r2/virtual_reality_lab/exporting_data/labvr_exportallobserverimages.md) 要求文件包含观察视角。
- 若导出的名称包含真实 H/V 角度，GIF 左上角会用内嵌 **Arial Regular** 标注白字黑描边的角度。字号可调整。每个 V 生成独立 GIF，H 升序；`collection_all_angles.gif` 按 V 降序、H 升序排列。
- 若 COM 导出名称只有索引，先从源文件的已验证 XML 角度表恢复 H/V，并转换弧度为度。仅在元数据布局、索引网格、导出数量完整匹配时恢复；未知布局、立体模式或不完整网格会明确记录原因，再按索引生成 `collection_all_views.gif`，此时不标注角度、不分组且必须清除筛选。未修改原始视角文件。
- 单视角只生成静态 GIF，不会生成新的相机视角。导出使用文件打开后的默认配置与显示设置，不修改源文件。

GIF 最多 256 色，透明像素合成到黑色背景。延时为 10–655350 ms，以 10 ms 记录，如 305 实际为 300 ms。字号范围 1–512。所有选中视角须尺寸一致；大量高分辨率素材仍会占用较多内存。

## 拖放和任务保护

拖入区域会在可接收时高亮，离开后恢复。整个窗口可接收文件，含中文、空格、花括号的路径按 Tcl 文件列表正确解析。一次仅接收一个文件；错误格式、文件夹、多文件或不存在的文件会显示提示，并保留原输入与输出。转换与关闭期间拒绝更换输入。

程序验证新 VRLab 实例的 PID、创建时间和完整路径后才打开文件，只关闭本次创建的实例。如果 Ansys 返回已有会话，请先保存并关闭 VRLab 后重试。启动或授权阶段取消时，若实例身份尚无法确认，可能需要手动关闭残留的 Ansys 窗口。

同名 GIF 在完整写入临时文件后才替换。取消或关闭窗口时，已完成的 GIF 保留，未完成文件清理。默认显示生成设置页，底部操作始终可见；窗口保持约 700×450（100% 缩放），并随显示缩放调整。默认 Dark，右上角可切换 Light，切换保留页面、数据与进度。

主题按钮参考本机 ACT-WBEX-Updater 的 132×34 分段按钮，使用固定 Dark / Light 标签与一个滑动选中块。Tab 可聚焦，左右键或 Home/End 直接选择，空格或 Enter 切换。按下即有反馈，移出按钮后松开会取消选择；动画可随时反向。系统关闭客户端区域动画时停止滑动，键盘选择立即完成。颜色和圆角适配本程序，未引入对 ACT 项目的运行依赖。

## 源码运行与打包

需要 Python 3.10+（含 Tkinter）：

```powershell
python -m pip install -r requirements.txt
python main.py
```

构建：

```powershell
.\build.ps1 -OutputDirectory 'dist\1.2.4'
```

构建自动安装依赖、运行测试、检查字体与拖放桥接，然后生成单文件 EXE 和 ZIP。可用 `-Python 'C:\path\python.exe' -SkipInstall` 复用已配置环境。PyInstaller 包含 tkinterdnd2 的原生 Tk 扩展；字体缺失时构建会报错，详见 [字体资源说明](docs/fonts.md)。

## 验证

```powershell
python -m unittest discover -s tests -v
python main.py --smoke-test
```

测试覆盖编码、排序、筛选、原生导出隔离、取消、损坏文件、保留旧结果、内嵌 Arial、紧凑布局、主题和拖放。GUI 测试只替代外部 Ansys 导出步骤，仍实际编码 GIF。拖放测试加载原生 tkdnd 扩展，并经过 Windows OLE 到 Tk 的事件桥验证路径与动作；源码及打包 EXE 的自检均验证该桥接，不会启动 Ansys。

发布构建会运行自动测试以及源码、EXE 的字体、拖放与 PPT 导出自检。样例来源和历史实测记录保存在 `samples/ansys-vrlab/`；大型下载文件及生成的 GIF、PNG、PPT 不进入 Git 仓库。

内部 PNG 解码和测试用于处理 Ansys 自动导出的中间帧，不提供用户 PNG 文件夹入口。

本机 VRLab 2024 R1 已验证官方 OptisVR 的 3 个视角，以及 AR speos360 的 35 个视角。后者的角度为 H=−0.30° 至 0.30°、V=−0.20° 至 0.20°；程序恢复的 35 个角度文件名与用户手动导出一致。其他 Ansys 版本尚未逐一实测。实际 COM 验证可显式执行：

```powershell
python tools/verify_native_conversion.py samples/ansys-vrlab/test_07_VRLab_export.OptisVR --output samples/ansys-vrlab/v1.2.0-conversion --helper-executable dist/1.2.0/VRLab2GIF.exe
```

界面截图：`python tools/preview_ui.py --theme dark --output docs/dark-mode.png`，将主题改为 light 可截取浅色界面；使用 `--page filters` / `--page logs` 选择辅助页面。

原生拖放组件采用 [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2)，其项目许可为 MIT；组件与所含 TkDnD 的原始许可见分发包 `docs/third-party/`。

开发公司：Intelligent Efficiency Team

Copyright © Intelligent Efficiency Team
