using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;
using System.Drawing;
using System.Text.RegularExpressions;
using System.Threading;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// Windows Framework is available on the target OS; Node and Python travel with the package.
// Shell order: embedded WebView2 window (preferred) -> external Edge/Chrome app window when the
// WebView2 Runtime or the native loader is unavailable, so locked-down machines still work.
internal static class Launcher {
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles();
        if (args.Length > 0 && args[0] == "--pick-folder") {
            using (var dialog = new FolderBrowserDialog()) {
                dialog.Description = "选择预算分析报告输出文件夹";
                if (dialog.ShowDialog() == DialogResult.OK) {
                    var output = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false));
                    output.Write(dialog.SelectedPath); output.Flush();
                }
            }
            return;
        }
        string root = AppDomain.CurrentDomain.BaseDirectory;
        // The installer checks this named object before replacing or removing files.
        using (var running = new Mutex(false, ReadSetting(root, "mutexName"))) {
        try { Application.Run(new Host(root)); }
        catch (Exception e) { MessageBox.Show("启动失败：" + e.Message + "\n请确认已完整解压安装包。", "衡策 · 启动检查", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }
    }
    static string ReadSetting(string root, string key) {
        var config = File.ReadAllText(Path.Combine(root, @"desktop\distribution.json"), Encoding.UTF8);
        var match = Regex.Match(config, "\"" + key + "\"\\s*:\\s*\"([A-Za-z0-9.-]+)\"");
        if (!match.Success) throw new Exception("安装包配置无效：" + key);
        return match.Groups[1].Value;
    }
    sealed class Host : ApplicationContext {
        Process server; NotifyIcon tray; string url; string browser; string profile; string data; Form window; bool externalMode; bool exiting;
        public Host(string root) {
            string env = Environment.GetEnvironmentVariable("FINAGENT_DATA_DIR");
            if (String.IsNullOrEmpty(env)) {
                env = Path.Combine(@"D:\衡策数据\1.0.5", ReadSetting(root, "dataFolder"));
            }
            if (!Path.GetFullPath(env).StartsWith(@"D:\", StringComparison.OrdinalIgnoreCase))
                throw new Exception("数据目录必须位于 D 盘");
            data = env;
            Directory.CreateDirectory(data);
            Environment.SetEnvironmentVariable("TEMP", data);
            Environment.SetEnvironmentVariable("TMP", data);
            profile = Path.Combine(data, "browser-profile");
            string[] browsers = {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Microsoft\Edge\Application\msedge.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Microsoft\Edge\Application\msedge.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Google\Chrome\Application\chrome.exe") };
            foreach (string candidate in browsers) if (File.Exists(candidate)) { browser = candidate; break; }
            var start = new ProcessStartInfo(Path.Combine(root, @"runtime\node.exe"), "\"" + Path.Combine(root, @"desktop\server.mjs") + "\"");
            start.WorkingDirectory = root; start.UseShellExecute = false; start.CreateNoWindow = true;
            start.RedirectStandardOutput = true; start.RedirectStandardError = true;
            start.EnvironmentVariables["FINAGENT_DATA_DIR"] = data;
            start.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            server = Process.Start(start); server.ErrorDataReceived += (s,e) => {}; server.BeginErrorReadLine();
            var lineTask = server.StandardOutput.ReadLineAsync();
            if (!lineTask.Wait(30000) || String.IsNullOrEmpty(lineTask.Result)) { try { server.Kill(); } catch {} throw new Exception("本地服务启动超时"); }
            url = Regex.Match(lineTask.Result, @"http://127\.0\.0\.1:\d+").Value;
            if (String.IsNullOrEmpty(url)) throw new Exception("本地服务未返回有效地址");
            tray = new NotifyIcon { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath), Text = "衡策 · 智能预算分析", Visible = true };
            var menu = new ContextMenuStrip();
            menu.Items.Add("打开预算工作台", null, (s,e) => Open());
            menu.Items.Add("退出衡策", null, (s,e) => ExitThread());
            tray.ContextMenuStrip = menu; tray.DoubleClick += (s,e) => Open();
            Open();
        }
        void Open() {
            if (!externalMode && (window == null || window.IsDisposed)) {
                try { window = CreateWindow(); } catch { window = null; }
            }
            if (window != null) { window.Show(); window.Activate(); return; }
            OpenExternal();
        }
        Form CreateWindow() {
            // The native loader ships next to FinAgent.exe; without it fall back instead of crashing.
            if (!File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "WebView2Loader.dll"))) return null;
            var form = new Form();
            form.Text = "衡策 · 智能预算差异分析与风险预警系统";
            form.StartPosition = FormStartPosition.CenterScreen;
            form.Size = new Size(1440, 960);
            form.MinimumSize = new Size(1024, 640);
            form.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            var web = new WebView2();
            web.Dock = DockStyle.Fill;
            web.CreationProperties = new CoreWebView2CreationProperties();
            web.CreationProperties.UserDataFolder = Path.Combine(data, "webview-profile");
            bool failed = false;
            web.CoreWebView2InitializationCompleted += (s,e) => {
                if (e.IsSuccess) return;
                failed = true;
                try { if (!form.IsDisposed) form.Close(); } catch {}
            };
            form.FormClosed += (s,e) => {
                window = null;
                if (failed) SwitchToExternal();
                else ExitThread(); // closing the embedded window quits the whole application
            };
            form.Controls.Add(web);
            web.Source = new Uri(url);
            return form;
        }
        void SwitchToExternal() {
            externalMode = true;
            if (tray != null) {
                tray.BalloonTipTitle = "衡策 · 显示模式切换";
                tray.BalloonTipText = "未检测到 WebView2 运行时，已改用系统浏览器窗口。";
                try { tray.ShowBalloonTip(5000); } catch {}
            }
            OpenExternal();
        }
        void OpenExternal() {
            if (browser == null) {
                MessageBox.Show("未找到可用的显示组件（WebView2 运行时或 Microsoft Edge / Chrome）。", "衡策 · 启动检查", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            var start = new ProcessStartInfo(browser, "--app=" + url + " --user-data-dir=\"" + profile + "\" --no-first-run --no-default-browser-check --window-size=1440,960");
            start.UseShellExecute = false; start.CreateNoWindow = true;
            Process.Start(start);
        }
        protected override void ExitThreadCore() {
            if (exiting) return;
            exiting = true;
            if (tray != null) { tray.Visible = false; tray.Dispose(); }
            if (window != null && !window.IsDisposed) { try { window.Close(); } catch {} window = null; }
            if (server != null) { try { if (!server.HasExited) server.Kill(); } catch {} server.Dispose(); }
            base.ExitThreadCore();
        }
    }
}
