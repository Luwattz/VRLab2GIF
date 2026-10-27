# Virtual Reality Lab 视角合成器

**1.2.5**：项目采用 MIT 许可证，单文件与文件夹分发包均附带 `LICENSE`。整合最新 PNG 文件夹导入、VRLab COM 注册指引、界面布局及日志滚动修复，并同时提供两种 Windows x64 分发包。

**1.2.4**：主题切换改为 Windows 整体画面合成，解决日志标题、按钮栏等控件分批重绘造成的横纹。大卡片使用缓存圆角切片，减少首次切页停顿；两个滑块按 60 Hz 帧预算调度，动画期间临时提高 Windows 定时精度，结束即释放。

Dark / Light 切换时，主体作为完整画面统一渐变，标题栏与顶部选择器同步配色。支持途中反向选择，默认仍为 Dark；本机 150% 缩放下动画帧间隔通常约 17 ms，性能及限制详见 [主题过渡说明](docs/theme-transition.md)。

右上角保留 ACT-WBEX-Updater 风格的分段按钮，两个标签固定显示，选中块平滑滑动，支持快速反向切换、按下取消及键盘操作，并遵循 Windows 动画设置。

从 `.OptisVR` / `.speos360` 或已导出的 PNG 图片文件夹生成 GIF，支持拖入输入、真实 H/V 角度标注及筛选、垂直角度分组和 PowerPoint 导出。PPT 首页展示全角度合集；版权、开发公司及默认页脚为 Intelligent Efficiency Team。

VRLab 2024 R1 的 COM 导出文件名使用索引，与手动菜单导出的角度文件名不同。本程序从已验证的源文件元数据恢复真实 H/V 角度，详见 [调查与验证](docs/observer-angles.md)。

支持导出 PowerPoint。GIF 生成成功后，点击底部“导出 PPT…”，填写标题、页脚、内容范围和保存位置。每个 GIF 一页，保留完整动画。PPT 采用 LumiDyna 的微软雅黑橙色标题、母版上下横线、页脚和自动页码，详见 [PPT 导出说明](docs/ppt-export.md)。

恢复初版的 PNG 文件夹导入入口：点击“PNG 文件夹…”或拖入一个已导出图片的文件夹，即可直接编码 GIF，无需安装 Ansys，输入 PNG 保持不变。选择原生视角文件时，程序仍会调用本机 Ansys VRLab 导出观察视角并生成 GIF，自动清理本次导出的中间 PNG。

[Dark 界面](docs/dark-mode.png) · [Light 界面](docs/light-mode.png) · [角度筛选页](docs/angle-filters.png) · [运行日志页](docs/runtime-logs.png)

## 使用

正式发布页位于 [GitHub Releases](https://github.com/Luwattz/VRLab2GIF/releases/latest)。本地构建默认同时生成单文件版和文件夹版，两版功能一致，均无需安装 Python，并附带 Arial 与原生拖放组件。

| 版本 | 本地运行入口（以 `dist/1.2.5` 为例） | 分发包 |
| --- | --- | --- |
| 单文件版 | `dist/1.2.5/VRLab2GIF.exe`，可单独复制运行 | `VRLab2GIF-Windows-x64.zip`，附说明文档 |
| 文件夹版 | `dist/1.2.5/VRLab2GIF/VRLab2GIF.exe`，保留整个目录及 `_internal` | `VRLab2GIF-Windows-x64-folder.zip`，完整解压后运行 |

文件夹版可用于单文件版启动较慢的终端。单文件版启动时会先将内置依赖展开到临时目录，文件夹版直接使用随包附带的依赖，参见 [PyInstaller 官方说明](https://pyinstaller.org/en/v6.16.0/operating-mode.html#how-the-one-file-program-works)。

1. 点击“视角文件…”选择一个 `.OptisVR` 或 `.speos360` 文件，或点击“PNG 文件夹…”选择已导出的图片目录。也可以拖入一个文件或文件夹，或手动填写路径。
2. 原生文件默认输出到同级的 `文件名_GIF` 文件夹；PNG 目录默认输出到同级的 `完整目录名_GIF` 文件夹（如 `导出.v1` 对应 `导出.v1_GIF`）。输出位置可更改，自定义后更换输入会保留该位置。
3. 在“生成设置”页设置每帧延时（默认 300 ms）和角度字号（默认 24 px）；按需切到“角度筛选”页填写范围。
4. 点击“开始生成 GIF”。PNG 文件夹直接编码；原生文件先通过 Ansys 导出视角。拖入只选择输入，不会自动启动转换。
5. 完成后点击“打开输出”。生成时可切到“运行日志”页查看过程，Esc 取消，Ctrl+Enter 开始。
6. 如需汇报文件，点击“导出 PPT…”，选择全部已生成 GIF 或仅合集，再导出。设置界面可查看 [Dark 预览](docs/ppt-export-dark.png) / [Light 预览](docs/ppt-export-light.png)。生成 PPTX 不要求安装 PowerPoint；动画在桌面 PowerPoint 的幻灯片放映中播放。

分页切换保留输入路径、参数、角度范围、日志和各页滚动位置。Ctrl+Tab / Ctrl+Shift+Tab 可前后切页。角度筛选标签显示“已设”或“检查”，提醒隐藏页上的筛选仍然生效；清除筛选后恢复普通标签。生成中分页仍可切换，处理失败自动显示日志页；在其他页面拖入新文件或文件夹会返回生成设置页。

分页设计参考 apple-design 技能中的导航定位、分组、字体层级和即时反馈原则；该技能没有专门的分页模板，共享底座和选中块是针对本应用的具体设计。控件使用系统字体，分页和主题均采用分段滑块并保留键盘操作；切换立即响应，Dark/Light 配色及显示缩放同步适配。

原生视角文件转换需要 **Windows、本机已安装并注册的 Ansys Virtual Reality Lab，以及可用授权**。导出接口要求显示 VRLab 窗口，运行期间会短暂出现。首次验证原生文件转换建议使用 [官方样例](samples/ansys-vrlab/README.md)，角度筛选留空。PNG 文件夹转换不调用 Ansys。

## 已安装 Speos，但提示 VRLab 自动化未注册

安装了 Speos、能够手动打开 `.OptisVR` / `.speos360`，并不代表 VRLab 的 COM 自动化接口已经注册。导入原生视角文件时，本程序会只读检查注册信息；未检测到可用注册时，显示注册指引和 PNG 文件夹替代入口。

可先按以下步骤完成一次注册：

1. 保存文件，关闭所有 VRLab 窗口。
2. 在所用 Speos 版本的安装目录中找到 `VRLab.exe`，通常位于 `Optical Products\Viewers`。多版本并存时，选择本次需要调用的版本。
3. 右键 `VRLab.exe` → **以管理员身份运行**，等待主界面完整打开，再正常退出。
4. 按普通用户方式运行 VRLab2GIF，重新点击“开始生成 GIF”检查并重试。

这是一次性的自动化注册操作，完成后无需每次生成 GIF 都以管理员权限运行本程序。Ansys 对通过管理员启动指定版本 Viewer 来注册自动化入口的说明，见 [Speos Labs Automation 2024 R2 的 Before starting 部分](https://developer.ansys.com/docs/speos-labs-automation-2024-r2/lab_api_home.md)。

没有管理员权限时，可以请 IT 协助完成上述操作；也可以正常打开 VRLab，手动导出带真实 H/V 角度文件名的 PNG，再点击本程序的“PNG 文件夹…”直接生成 GIF。该路径不需要 COM 注册或管理员权限，文件命名要求见下节。本程序只提供检查和操作指引，不会自动提权或修改注册表。

## 输入范围与角度标记

- 原生文件方式接收 `.OptisVR` / `.speos360` 中已有的观察视角。
- PNG 文件夹方式只扫描所选目录的当前层，不扫描子目录。图片须按 `<前缀>_Image_<H>°_<V>°.png` 命名，例如 `demo_Image_-30°_10°.png`；不符合格式的 PNG 会跳过并记录到日志。PNG 单图应放入文件夹后导入。
- 尚不支持沉浸式全景及 XMP、EXR、HDR、PIC。这些格式需要另行开发渲染流程。所用 [官方导出接口](https://developer.ansys.com/docs/speos-labs-automation-2024-r2/virtual_reality_lab/exporting_data/labvr_exportallobserverimages.md) 要求文件包含观察视角。
- 对符合角度命名格式的 PNG（包括手动导入的文件夹），GIF 左上角会用内嵌 **Arial Regular** 标注白字黑描边的角度。字号可调整。每个 V 生成独立 GIF，H 升序；`collection_all_angles.gif` 按 V 降序、H 升序排列。两种输入均使用当前每帧延时、字号和角度筛选设置。
- 若 COM 导出名称只有索引，先从源文件的已验证 XML 角度表恢复 H/V，并转换弧度为度。仅在元数据布局、索引网格、导出数量完整匹配时恢复；未知布局、立体模式或不完整网格会明确记录原因，再按索引生成 `collection_all_views.gif`，此时不标注角度、不分组且必须清除筛选。未修改原始视角文件。
- 单视角只生成静态 GIF，不会生成新的相机视角。导出使用文件打开后的默认配置与显示设置，不修改源文件。

GIF 最多 256 色，透明像素合成到黑色背景。延时为 10–655350 ms，以 10 ms 记录，如 305 实际为 300 ms。字号范围 1–512。所有选中视角须尺寸一致；大量高分辨率素材仍会占用较多内存。

## 拖放和任务保护

拖入区域会在可接收时高亮，离开后恢复。整个窗口可接收输入，含中文、空格、花括号的路径按 Tcl 文件列表正确解析。一次仅接收一个原生视角文件或一个 PNG 文件夹；PNG 单图、其他格式、多个路径或不存在的路径会显示提示，并保留原输入与输出。转换与关闭期间拒绝更换输入。

原生文件转换时，程序验证新 VRLab 实例的 PID、创建时间和完整路径后才打开文件，只关闭本次创建的实例。如果 Ansys 返回已有会话，请先保存并关闭 VRLab 后重试。启动或授权阶段取消时，若实例身份尚无法确认，可能需要手动关闭残留的 Ansys 窗口。

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
.\build.ps1 -OutputDirectory 'dist\1.2.5'
```

每次构建都会同时生成单文件 EXE、文件夹版和两种 ZIP，不需要额外切换打包参数。两版复用同一份依赖分析、代码和资源；各自从发布目录运行自检，验证字体、文件及文件夹拖放、PNG→GIF 和 PPT 导出后再打包，并分别附带说明文档与许可。直接构建 `VRLab2GIF.spec` 也会同时输出两种程序形态。

构建自动安装依赖并运行测试；可用 `-Python 'C:\path\python.exe' -SkipInstall` 复用已配置环境。PyInstaller 包含 tkinterdnd2 的原生 Tk 扩展；字体缺失时构建会报错，详见 [字体资源说明](docs/fonts.md)。

## 验证

```powershell
python -m unittest discover -s tests -v
python main.py --smoke-test
```

测试覆盖编码、排序、筛选、原生导出隔离、取消、损坏文件、保留旧结果、内嵌 Arial、紧凑布局、主题和拖放。GUI 测试只替代外部 Ansys 导出步骤，仍实际编码 GIF。拖放测试加载原生 tkdnd 扩展，并经过 Windows OLE 到 Tk 的事件桥验证路径与动作；源码及打包 EXE 的自检均验证该桥接，不会启动 Ansys。

发布构建会运行自动测试以及源码、EXE 的字体、拖放与 PPT 导出自检。样例来源和历史实测记录保存在 `samples/ansys-vrlab/`；大型下载文件及生成的 GIF、PNG、PPT 不进入 Git 仓库。

PNG 文件夹转换复用原有 PNG 编码流程，保留角度筛选、分组、排序、取消和已完成 GIF 的 PPT 导出功能；输入 PNG 不会被修改或清理。

本机 VRLab 2024 R1 已验证官方 OptisVR 的 3 个视角，以及 AR speos360 的 35 个视角。后者的角度为 H=−0.30° 至 0.30°、V=−0.20° 至 0.20°；程序恢复的 35 个角度文件名与用户手动导出一致。其他 Ansys 版本尚未逐一实测。实际 COM 验证可显式执行：

```powershell
python tools/verify_native_conversion.py samples/ansys-vrlab/test_07_VRLab_export.OptisVR --output samples/ansys-vrlab/v1.2.0-conversion --helper-executable dist/1.2.0/VRLab2GIF.exe
```

界面截图：`python tools/preview_ui.py --theme dark --output docs/dark-mode.png`，将主题改为 light 可截取浅色界面；使用 `--page filters` / `--page logs` 选择辅助页面。

## 许可证

本项目采用 [MIT License](LICENSE)，Copyright (c) 2026 Intelligent Efficiency Team。源码、单文件 EXE 内及两种分发包均包含该许可证。

第三方组件、字体及 Ansys 样例保留各自原有许可，不属于本项目 MIT 授权范围。Arial 的来源及权利说明见 [字体资源说明](docs/fonts.md)，Ansys 样例许可见 [LICENSE-ANSYS.txt](samples/ansys-vrlab/LICENSE-ANSYS.txt)。

原生拖放组件采用 [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2)，其项目许可为 MIT；组件与所含 TkDnD 的原始许可见分发包 `docs/third-party/`。

开发公司：Intelligent Efficiency Team

Copyright © Intelligent Efficiency Team
