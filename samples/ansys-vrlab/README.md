> 仓库只保存样例来源、许可及验证说明；大型视角文件与生成结果保留在本机，未上传 Git。请按下方官方来源下载样例。旧版本号和结果路径是开发阶段的历史记录，当前正式版本为 1.2.0。

# Ansys Virtual Reality Lab 官方验证样例

已下载：`test_07_VRLab_export.OptisVR`，15,793,012 字节，约 15.1 MiB。

这是 Ansys 官方 Optical Automation 仓库用于 VRLab 视角导出的测试文件。样例及附带许可按仓库中的 MIT License 提供，见 `LICENSE-ANSYS.txt`。

## 来源

- [官方样例文件](https://github.com/ansys/optical-automation/blob/main/tests/workflows/example_models/test_07_VRLab_export.OptisVR)
- [官方测试流程](https://github.com/ansys/optical-automation/blob/main/tests/workflows/run_test_07_VRLab_export.py)
- [官方导出结果参考](https://github.com/ansys/optical-automation/blob/main/tests/workflows/test_07_VRLab_reference_results.json)
- [Virtual Reality Lab 导出所有视角说明](https://ansyshelp.ansys.com/public/views/secured/corp/v242/en/Optis_UG_LAB/Optis/UG_Lab/T_UG_LAB_vr_lab_exporting_all_views.html)

## 如何验证 VRLab2GIF

VRLab2GIF **1.5.0 仅通过视角文件生成 GIF，支持文件拖入**。本机须安装 Ansys Virtual Reality Lab 且授权可用。

1. 打开 `dist/1.5.0/VRLab2GIF.exe`，将本目录的 `test_07_VRLab_export.OptisVR` 拖入窗口，或点击“选择文件…”。
2. 延时保持 300 ms，角度筛选留空，点击“开始生成 GIF”。
3. 默认输出为本目录下的 `test_07_VRLab_export_GIF/collection_all_views.gif`，无需手动打开 VRLab 或导出 PNG。

已在 VRLab 2024 R1 实测：导出 3 张 3840×2160 PNG，并生成 3 帧、300 ms、无限循环 GIF。可查看 `direct-conversion/verification.json` 及 `direct-conversion/collection_all_views.gif`。

打包后的 1.4.0 EXE 也已完成真实 COM 导出验证，见 `packaged-conversion/verification.json` 和对应 GIF；打开文件阶段的取消验证通过，未留下未完成输出。验证日期：2026-10-25。

此样例的 COM 导出名称为 `_Image_0_0.png`、`_Image_1_0.png`、`_Image_2_0.png`，旧版因此仅按数字序号合成。**1.7.1 调查更正**：原始文件的 XML 头实际保存了角度表，H 为 −100°、−95°、−90°，V 为 0°；现已读取并恢复，支持标注、筛选和分组。原先“没有真实角度”的判断仅基于导出文件名，不适用于源文件内容，详见 `../../docs/observer-angles.md`。

1.5.0 EXE 也已完成实际导出与 GIF 编码，3 帧均为 3840×2160、300 ms，结果见 `v1.5.0-conversion/collection_all_views.gif` 和 `verification.json`。

仓库的参考测试以 JPG 导出，记录了 3 张视角图片；附带 `reference_results.json` 供追溯。1.5.0 已移除 PNG 文件夹入口，用户只需选择原始视角文件，PNG 中间帧由程序自动处理。

## 文件完整性

下载内容已与 GitHub 返回的文件长度及 Git blob SHA-1 对照，一致：

- Git blob SHA-1：`a0165325c731235ecfce66d89c4203ec28e9827e`
- SHA-256：`30daf18b8d7a78d02e2f18c64325e0aac3a1e31bac28fce900ded60b08365272`

已校验下载文件完整性，并在本机 VRLab 2024 R1 实际打开、导出和合成验证。

下载日期：2026-10-24。
