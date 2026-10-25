# VRLab2GIF 应用标识

设计主题：**视角成帧**。叠合画帧代表 PNG 序列；环绕箭头代表 H / V 视角变化与循环；播放符号代表合成后的动画。蓝色底座、白色主体与浅青色轨迹配合现有的 Apple Design 风格界面。

## 交付文件

- `vrlab2gif-logo.png`：透明背景的高清应用图标，保留生成图像的原始分辨率。
- `vrlab2gif.ico`：Windows 多尺寸图标，包含 16、20、24、32、40、48、64、96、128、256 像素。

PNG 用于程序标题区和窗口图标；ICO 嵌入 Windows EXE。所有资产随项目保存，并包含在分发压缩包的 `assets/` 文件夹内。

## 生成方式

使用 imagegen 技能及内置图像生成功能生成，并验证小尺寸应用效果。保留原始 PNG 的透明通道。ICO 仅做格式和尺寸转换，未改变设计。

## 初始提示词（原文）

```text
Use case: logo-brand.
Asset type: production desktop application icon for VRLab2GIF, a utility that turns PNG images captured at different horizontal and vertical viewing angles into looping GIF animations.
Primary request: design one original, highly polished icon consistent with a calm Apple-inspired productivity application. The symbol combines two overlapping rounded rectangular picture frames with one bold, graceful orbital sweep around them, expressing multiple viewpoints becoming a single moving image. The foreground frame includes one simple small triangular play cutout. The orbit should have a single clear directional terminal, with deliberate negative space and no tiny decoration.
Style: exceptionally clean vector-like geometric shapes, precise curves, restrained depth, premium macOS app-icon craft. Strong legibility at 32px. A solid blue rounded-square tile with a very subtle azure-to-cobalt gradient, crisp white primary symbol, one pale-cyan orbital accent. No photorealistic material and no heavy 3D extrusion.
Composition: square canvas, a single large centered icon, front-facing. The rounded square occupies about 92% of the canvas with even transparent margins and smooth fully transparent corners outside the tile. All marks remain comfortably within the tile. Balanced optical weight, bold strokes, clean silhouettes.
Text: none. No letters, numbers, captions, degree labels, wordmark, Apple emblem, watermark, presentation board, devices, or mockup scene. Output the actual application icon asset with a genuinely transparent background outside the blue rounded square.
```


