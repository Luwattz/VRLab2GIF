# GIF 角度标记字体

1.4.1 在 EXE 中内嵌 Arial Regular。单独复制 EXE 即可使用，无需在目标电脑安装 Arial 或另外复制 fonts 文件夹。

源码资源为 `fonts/arial.ttf`，Pillow 直接读取 TTF，不向 Windows 字体目录或注册表安装字体。PyInstaller 运行时将资源解压到临时目录，程序优先加载该目录中的 Arial。

字体用于 GIF 的 H/V 角度标记，默认 24 px、白字黑描边，不改变桌面界面的系统字体。没有真实角度信息的视角序列仍不添加角度文字。

资源来源：本机 `C:\Windows\Fonts\arial.ttf`，保留原始文件及其中的版权信息。字体权利属于原权利人，程序自身的许可不包含字体再分发授权。

- 文件长度：1,045,720 字节
- SHA-256：`b3658eadae55e682b5f69eb64c439c1ecc8f196c0bb8d4756d145d13bc86476a`

构建时字体缺失会报错。源码与 EXE 的 `--smoke-test` 检查实际加载的是内嵌 Arial；自动测试还模拟无法访问系统字体的环境，验证带角度文字的 GIF 正常生成。
