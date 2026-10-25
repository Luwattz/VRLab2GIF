> 仓库只保存样例来源、许可及验证说明；大型视角文件与生成结果保留在本机，未上传 Git。请按下方官方来源下载样例。旧版本号和结果路径是开发阶段的历史记录，当前正式版本为 1.2.0。

# 多视角官方样例

## AR Observer：已验证 35 个视角

- 文件：`AR_Observer_520nm.speos360`，57,293,320 字节。
- 来源：[Ansys Augmented Reality Optical System](https://optics.ansys.com/hc/en-us/articles/12157334700435-Augmented-Reality-Optical-System)。
- [完整案例下载入口](https://api.lumerical.com/app-gallery/fetch-download-web?id=c118296f-augmented-reality-optical-system)，完整 ZIP 约 2.05 GB；这里只分段提取了所需的 Observer 文件，并由 Python zipfile 校验 CRC。
- 原始压缩包路径：`Speos Results files/SPEOS output files/Inverse FDTD Observer 520nm.Observer FHD 520nm.speos360`。
- SHA-256：`9c52566062c7089534040c06b049bf6b73d9f804c479195ad625cea4b80e89a3`。
- 保留原包许可 `AR-license.txt`、元数据 `AR-metadata.json`、来源 `AR_Observer_520nm-source.json` 和压缩包文件目录。

验证日期：2026-10-25。使用本机 Ansys Virtual Reality Lab 2024 R1 和本项目现有转换逻辑，实际导出 **35 个视角**；生成 `AR_Observer_520nm-gif/collection_all_views.gif`，35 帧，每帧 1600×1000、300 ms，无限循环。解码后的 35 帧哈希各不相同，详见同目录的 `verification.json`。

**1.7.1 更正**：文件实际保存了完整角度表，旧版仅因 COM 导出名称使用索引而未读取角度。现在从源文件恢复 H/V；35 个还原文件名与用户手动导出完全一致。H=−0.30° 至 0.30°，V=−0.20° 至 0.20°，间隔 0.10°。支持角度标注、筛选和分组，详见 `../../../docs/observer-angles.md`。

将 `AR_Observer_520nm.speos360` 拖入 1.7.1 即可测试。新版本实测结果保存至 `AR_Observer_520nm-v1.7.1`；上面的 `AR_Observer_520nm-gif` 是旧版无角度结果，保留作对照。

AR 案例包另有 Ambient Observer（约 761 MB）和 Combined Observer（约 825 MB）结果。本次仅核实了它们的压缩包条目，未下载或验证这两个结果。

## HUD：只有工程，没有现成 Observer 结果

[Ansys Head-Up Display 案例](https://optics.ansys.com/hc/en-us/articles/10072384186899-Head-Up-Display-HUD)的下载包为 `head-up-display-hud.zip`，6,781,795 字节。已检查 13 个条目，包含工程与预设，**不含 `.OptisVR` 或 `.speos360` 结果文件**，不能直接拖入本程序生成 GIF。留存包内许可 `HUD-license.txt` 和文件目录供核对。

## 旧格式样例

上级目录的 `test_07_VRLab_export.OptisVR` 是 Ansys Optical Automation 官方公开样例，已验证含 3 个视角。此次公开搜索未找到另一个可直接下载并验证的旧扩展名 `.OptisVR` 多视角文件。

Ansys 2021 R2 发布说明记录 `.optisVR` 扩展名改为 `.speos360`：https://storage.ansys.com/doc_assets/release_notes/v212/Release_Notes_2021_R2.pdf 。当前程序支持两种扩展名；本次 AR 文件保留原扩展名。
