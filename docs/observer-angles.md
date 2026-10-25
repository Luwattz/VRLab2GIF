# 直接转换：直接转换的角度信息恢复

调查日期：2026-10-25，本机 Ansys Virtual Reality Lab 2024 R1。

## 原因

用户手动通过 File → Export all views 导出的文件位于 `C:\Users\chimp\Desktop\1`，例如：

`AR_Observer_520nm_Image_-0.30°_-0.20°.png`

本程序调用 `ExportAllObserverImages(directory, 1)`，同一视角却命名为：

`AR_Observer_520nm_Image_0_0.png`

该接口返回的是 H/V 的角度表下标。旧程序仅解析 PNG 文件名，没有进一步读取源文件元数据，因而错误地把“接口文件名未提供角度”当成了无法取得角度。原有 Arial 绘字逻辑仍在，只是没有走到它。

源文件的压缩 XML 头包含 `PictureIndexerHeader/PhiList`、`ThetaList`、`NumberOfPicture` 和 `PictureOrder`；角度表以弧度储存。35 视角 AR 样例的 H 表换算后为 −0.30°、−0.20°、−0.10°、0°、0.10°、0.20°、0.30°，V 表为 −0.20°、−0.10°、0°、0.10°、0.20°。

## 对应关系验证

逐一比较了用户的 35 张手动 PNG（884×481，包含窗口显示比例的留黑）与 COM 原生分辨率 PNG（1600×1000）。将 COM 图像按比例缩放并居中后，35 张图像都唯一匹配到预期的索引，绿色通道缩略图相关系数最低约 0.996。匹配报告保存为 `samples/ansys-vrlab/additional/angle-investigation/visual-matches.json`。

例如 `0_0` 对应 H=−0.30°、V=−0.20°；`3_2` 对应 H=0°、V=0°；`6_4` 对应 H=0.30°、V=0.20°。用源文件角度表还原后的 35 个文件名集合与手动导出完全一致。此映射来自元数据并经过图片核对，并非把索引当成度数。

## 修复行为

COM 导出后，只读取源文件的压缩 XML 头，检查文件标识、版本、长度、完整解压、索引类型、角度表、图片顺序及导出网格，再重命名程序自己的临时 PNG。角度换算为度，按手动导出相同的两位小数格式恢复。

随后复用原有合成逻辑：Arial 白字黑描边显示角度、H/V 筛选、每个 V 单独生成 GIF，以及按 V 降序、H 升序生成合集。AR 样例应得到 5 个 7 帧分组 GIF 和 1 个 35 帧合集。

不修改原始视角文件和用户的手动 PNG。元数据读取最多 4 MiB，并拒绝 XML 实体声明及异常解压数据。当前只启用实际检查过的 MultiPictures 2.0、矩形单眼网格、升序角度表、顺序图片布局。其他布局、立体文件、精度导致角度合并的网格等会记录原因并保留索引模式，避免标错角度。此兼容范围并非 Ansys 公开文件格式规范。

## 复现

```powershell
python tools/verify_native_conversion.py samples/ansys-vrlab/additional/AR_Observer_520nm.speos360 --output samples/ansys-vrlab/additional/AR_Observer_520nm-v1.7.1 --helper-executable dist/1.2.0/VRLab2GIF.exe
```

旧版无角度的样例 GIF 保留作历史对照；新结果写入独立的 `AR_Observer_520nm-v1.7.1` 目录。
