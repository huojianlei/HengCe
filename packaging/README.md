# Windows 构建与交付 1.0.4

默认构建正式版；演示版（实验变体）必须显式指定。两者使用独立安装登记、桌面快捷方式和用户数据目录。

**1.0.4 壳变更**：Launcher 内嵌 WebView2 显示界面（自有窗口，不再拉起外部浏览器）。WebView2 运行时不可用时自动回退旧方案（外部 Edge/Chrome app 窗口）并气泡提示；正常关闭窗口即退出整个应用。构建需要 `packaging/libs/webview2/`（SDK 程序集 + x64 原生 Loader，见该目录 VERSION.txt），csc 编译新增两处引用，产物旁需同置 `Microsoft.Web.WebView2.Core.dll`、`Microsoft.Web.WebView2.WinForms.dll`、`WebView2Loader.dll`（构建脚本已自动处理）。

| 类型 | 程序载荷 | 安装及用户数据目录名 | 内置演示功能 |
| --- | --- | --- | --- |
| Production 正式版 | dist/FinAgent-Production | FinAgent | 完全不包含演示模块、演示入口、演示 JSON |
| Experimental 演示版 | dist/FinAgent | FinAgent-Experimental | 一键演示数据（固定演示集，无随机生成器） |

从项目根目录用 PowerShell 7 构建（PowerShell 5.1 亦可，脚本已带 BOM）：
```powershell
./packaging/build-all.ps1 -Flavor Experimental
./packaging/build-installer.ps1 -Package D:\AppProject\dist\FinAgent -OutputDirectory D:\AppProject\dist\releases\1.0.4\Experimental
./packaging/build-all.ps1 -Flavor Production
./packaging/build-installer.ps1 -Package D:\AppProject\dist\FinAgent-Production -OutputDirectory D:\AppProject\dist\releases\1.0.4\Production
```
已准备运行时后可向 build-all.ps1 加 -SkipRuntime。原 kb/env 与 Python312 只用于首次组装运行时，最终载荷内置依赖。build-installer.ps1 从 build-flavor.txt 读取类型，默认来源是正式载荷，避免误把演示功能封入正式包。Inno 编译器路径 tools/InnoSetup/ISCC.exe，可用 -Compiler 覆盖。

prepare-desktop.mjs 清理受控构建目录中的旧 web/experimental 资源，复制清单允许的文件。正式构建移除演示脚本入口与资源；同目录切换不会残留演示模块。服务端读取构建时静态清单，不提供演示运行开关。正式安装器在覆盖旧版本时移除已知的旧实验目录与 demo.json。演示模块源码在 desktop/experimental（entry.mjs 面板 + demo.json/reference.csv 固定演示集），与正式财务算法分离；演示集唯一源头是 desktop/scripts/make-demo.mjs。

安装支持 Windows 10/11 x64（Win11 出厂预装 WebView2；Win10 经更新推送，缺失时自动回退外部浏览器窗口）。单个 EXE 携带运行时、知识库和模型；静默部署参数 /VERYSILENT /SUPPRESSMSGBOXES /NORESTART，可加 /DIR="D:\Apps\FinAgent"。当前用户默认无需管理员权限。更新前从托盘或窗口退出应用；程序运行时安装或卸载会被阻止。标准卸载保留报告和设置。

验收记录位于 desktop/qa。演示数据触发与导入回归由 experimental.test.mjs 验证；演示页面（含导出真实 CSV）由 experimental-check.mjs 验证；载荷级导出全链（不装机）由 export-check.mjs 验证；正式包物理文件、静态入口、404 和真实 CSV 分析由 production-check.mjs 验证；安装/升级/运行/卸载由 test-experimental-installer.ps1（演示版 AppId）与 test-installer.ps1（正式版 AppId）验证。不要在已有用户安装上运行验收脚本（脚本会按设计拒绝）。归档组装与清单重算用 assemble-archive.ps1 / regen-archive-sha.ps1，交付说明文档源在 docs\交付说明\。
