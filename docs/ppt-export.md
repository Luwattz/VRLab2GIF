# 导出 PowerPoint

生成 GIF 成功后，底部“导出 PPT…”按钮可用。设置窗口使用上次成功生成的 GIF，可调整报告标题、页脚名称、导出全部 GIF 或仅合集、保存位置，以及完成后是否打开 PPT。“恢复默认”重置这些选项；程序运行期间保留上次使用的标题、页脚和内容选择。

导出不会再次调用 Ansys。每个 GIF 对应一页，**全角度合集固定放在首页**，其后保留各垂直角度分组的原有顺序；无角度元数据时，全视角合集同样优先。原始 GIF 文件完整嵌入 PPTX，包括帧、延时和循环信息。PPTX 可单独复制，不依赖原 GIF 文件。标题、页脚和图片位置可以在 PowerPoint 中继续编辑。

## LumiDyna 版式

参照本机 LumiDyna 项目的 `LumiDyna/report_style.py` 统一正文样式，以及其后处理报告的 960×540 pt 画布独立实现。LumiDyna 项目没有被修改，导出不需要运行该项目。

| 项目 | 参数 |
| --- | --- |
| 页面 | 16:9，960×540 pt，约 33.87×19.05 cm，白底 |
| 标题字体 | Microsoft YaHei（微软雅黑），24 pt，粗体 |
| 标题颜色 | RGB 255 / 168 / 79（#FFA84F） |
| 标题文本框 | 左 1.47 cm、上 0.50 cm、宽 25.00 cm、高 1.49 cm |
| 顶部横线 | 距顶部 1.99 cm |
| 底部横线 | 距底部 1.33 cm |
| 横线 | 左右各留 1.47 cm，RGB 230 / 212 / 194，0.75 pt |
| 内容 | 两条横线之间，上下再留 8 pt；GIF 等比例居中，不裁切、不拉伸 |
| 页脚 | 左下角默认 Intelligent Efficiency Team，可修改；微软雅黑 11 pt，RGB 118 / 106 / 96 |
| 页码 | 母版右下角原生 slidenum 自动字段，插入、删除或重排页面时由 PowerPoint 更新 |

PPT 使用白底参考样式，独立于程序 Dark/Light 外观。GIF 画面及其已有的 Arial 角度标记不会改成微软雅黑；微软雅黑用于 PPT 原生文字。

## 文件与播放

默认保存到已生成 GIF 所在目录，文件名为 `源文件名_report.pptx`；同名文件存在时自动建议 `_02` 等未占用名称。若手动指定已有文件，新 PPT 完整写入并校验成功后才替换。取消或失败会移除未完成文件，保留原 PPT 和 GIF。导出后“打开输出”定位到 PPT 保存目录；再次更改 GIF 输出路径时恢复该路径。

生成 PPTX 本身不要求安装 Office。查看动画建议使用桌面 Microsoft PowerPoint，并进入“幻灯片放映”；编辑视图可能只显示首帧。PowerPoint 网页版不能播放动画 GIF，见 [Microsoft 官方说明](https://support.microsoft.com/en-us/powerpoint/add-an-animated-gif-to-a-slide)。

标题过长、GIF 缺失或损坏会明确提示，不会裁掉标题或将动画静默变成首帧。当前输入仍仅为视角文件；不增加用户 PNG 文件夹或外部 GIF 导入入口。

## 验证

自动测试覆盖 PPTX 的部件关系、GIF 字节与动画帧、版式坐标、图片比例、母版自动页码、合集选择、标题转义及长度、损坏输入、取消和写入失败时保留旧文件，以及 GUI 异步导出流程。

官方 Ansys 样例生成的 GIF 已导出为 `samples/ansys-vrlab/ppt-export/VRLab2GIF_sample.pptx`，在本机 Microsoft PowerPoint 中实际打开、检查并渲染。导出的图片及字号/坐标检查记录位于同目录 `verification/`，不随软件分发。
