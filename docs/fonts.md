# GIF 角度标记字体

1.2.6 起内嵌 **Liberation Sans Regular 2.1.5**，替换原 Arial 文件。单文件版和文件夹版均不需要在目标电脑安装字体。

- 文件：`fonts/LiberationSans-Regular.ttf`，原始字体文件未作修改。
- 来源：[Liberation Fonts 官方 2.1.5 发布包](https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz)。
- 文件长度：410,712 字节。
- SHA-256：`76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8`。
- 版权：Copyright (c) 2010 Google Corporation；Copyright (c) 2012 Red Hat, Inc.；完整原始声明见 [LiberationFonts-LICENSE.txt](third-party/LiberationFonts-LICENSE.txt)。
- 许可：**SIL Open Font License 1.1**，保留字体名称 Liberation。允许免费商用、嵌入程序及随软件分发；保留版权与完整许可。字体本身不可单独销售；修改字体应遵守 OFL 对修改版和保留名称的规定。程序和输出 GIF/PPT 不因使用该字体而改用 OFL。

字体用于 GIF 的 H/V 角度标记，默认 24 px、白字黑描边。Liberation Sans 以 Arial 度量兼容为设计目标，字形和逐像素渲染仍有区别。没有真实角度的视角序列不添加文字，桌面界面继续使用系统字体。

Pillow 直接读取 TTF，不安装到系统字体目录或注册表。源码从 `fonts/` 加载，单文件程序从 PyInstaller 临时目录加载，文件夹版从 `_internal/fonts/` 加载。

构建时字体缺失会失败；`--smoke-test` 验证加载的是内嵌字体及正确家族。自动测试模拟禁止访问系统字体的环境并实际生成角度 GIF。字体版权与完整 OFL 文本会内嵌到 `third-party/`，并附于两种 ZIP 的 `docs/third-party/`。
