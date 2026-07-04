# KFPS - Kloudy's Forza Painter Suite

[English](README.md) | [中文](README.zh-CN.md)

这是 KFPS（Kloudy's Forza Painter Suite）的中文简短说明。完整、最新、最详细的文档目前以英文维护：

- 入门说明：[README.md](README.md)
- 完整用户手册：[docs/USER_MANUAL.md](docs/USER_MANUAL.md)
- FH6 模板/导入详细说明：[docs/FH6_IMPORT_GUIDE.md](docs/FH6_IMPORT_GUIDE.md)

## 最重要的使用流程

1. 下载最新版 release zip。
2. 解压整个文件夹，不要直接在 zip 里运行。
3. 打开 `KFPS.exe`。
4. 如果程序提示运行环境异常，在 Settings 里检查内置 runtime；完整 bundled 版本不需要手动安装 Python。
5. 如果显示有更新，可以在 `Update` 标签页更新。
6. 在 `Create` 页面选择一张或多张图片。
7. 选择适合图片类型的预设：
   - `Shaded Character Art`：动漫、人物、头发、眼睛、皮肤、混合线稿。
   - `Flat Colors`：贴纸、吉祥物、硬边、平涂区域。
   - `Smooth Gradients`：柔和阴影、渐变、高光过渡。
8. 设置 `Template layers` 为 FH6 模板的准确层数。
9. 普通用户默认不需要打开 Pro settings。Max resolution、Random samples、Mutated samples 会根据图片和预设自动计算。
10. 等到日志显示 `FINALIZE CHECKPOINTS COMPLETE`。
11. 在 FH6 里打开 Vinyl Group Editor，准备足够层数的模板，并确保模板已经 ungroup。
12. 在 `Outputs` 页面选择 finalized checkpoint，输入 FH6 模板的准确层数，然后导入。

## 关键规则

默认导入现在会把模板层数全部当作可用绘图层：

```text
可用绘图层数 = FH6 模板总层数
```

例子：

| FH6 模板层数 | 默认可用绘图层数 |
| ---: | ---: |
| 500 | 500 |
| 1000 | 1000 |
| 2000 | 2000 |
| 3000 | 3000 |

普通用户应该导入 `finals/` 里的 final JSON，不要导入 `checkpoints/` 里的 raw checkpoint。

`Image Tools` 标签页提供常用网页工具链接：背景移除、浏览器本地 2x/4x 放大、Squoosh 缩放/压缩。

`Editor` 标签页会管理项目并打开捆绑的本地 Fabric JSON 编辑器。它用于手工创建/编辑 FH6 JSON，不会写入 FH6 内存。

## 更新

推荐用原生 app 的 `Update` 标签页。也可以在 app 文件夹里运行：

```text
03_update_from_github.bat
```

更新前请关闭 app。更新器会保留 generated/runtime 输出。

## Credits / 致谢

本项目基于 Forza Painter 生态里的多个项目和贡献者。许可和署名保留在：

- [LICENSE](LICENSE)
- [LICENSE.geometrize-gpu](LICENSE.geometrize-gpu)
- [LICENSE.fabricjs](LICENSE.fabricjs)

主要来源和贡献包括：

| Person / project | Link | Contribution |
| --- | --- | --- |
| AE / A-Dawg#0001 | https://github.com/forza-painter/forza-painter | Original Forza Painter project and MIT-licensed import workflow. |
| BVZRays / bvz rays | https://github.com/bvzrays/forza-painter-fh6 | FH6-focused upstream work. |
| zjl88858 / forza-painter-geometrize-gpu | https://github.com/zjl88858/forza-painter-geometrize-gpu | GPU/OpenCL generator lineage. |
| Sam Twidale | https://samcodes.co.uk/ | `geometrize-lib` author. |
| Michael Fogleman | https://github.com/fogleman/primitive | `primitive` author. |
| Sanguk Ko / ree9622 | https://github.com/ree9622 | Korean localization contributor in upstream history. |
| heyitshestia / Kloudy | https://github.com/heyitshestia/kloudys-forza-painter-suite | This fork and current app workflow. |
