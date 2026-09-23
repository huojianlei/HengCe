using System;
using System.IO;
using System.IO.Compression;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Drawing;

// Self-contained installer: a ZIP is appended to this executable followed by its Int64 length.
internal static class Installer {
    [STAThread] static void Main(string[] args) {
        if(args.Length == 2 && args[0] == "--extract-to") {
            try { Extract(args[1], null); Environment.Exit(0); }
            catch { Environment.Exit(1); }
            return;
        }
        Application.EnableVisualStyles(); Application.Run(new Setup());
    }
    static void Extract(string destination, Action<int> progress) {
        string root=Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
        Directory.CreateDirectory(root);
        using(var input=File.OpenRead(Application.ExecutablePath)) {
            input.Seek(-8,SeekOrigin.End);var length=new BinaryReader(input).ReadInt64();
            if(length<=0 || length>input.Length-8 || length>Int32.MaxValue)throw new InvalidDataException("安装数据无效");
            input.Seek(-8-length,SeekOrigin.End);byte[] bytes=new byte[(int)length];
            int offset=0;while(offset<bytes.Length){int read=input.Read(bytes,offset,bytes.Length-offset);if(read==0)throw new EndOfStreamException();offset+=read;}
            using(var zip=new ZipArchive(new MemoryStream(bytes),ZipArchiveMode.Read)) {
                int count=0;
                foreach(var entry in zip.Entries) {
                    string target=Path.GetFullPath(Path.Combine(root,entry.FullName));
                    if(!target.StartsWith(root,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("安装路径不合法");
                    if(String.IsNullOrEmpty(entry.Name)){Directory.CreateDirectory(target);continue;}
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    using(var source=entry.Open())using(var output=File.Create(target))source.CopyTo(output);
                    count++;if(progress!=null)progress(count*100/zip.Entries.Count);
                }
            }
        }
    }
    sealed class Setup : Form {
        TextBox location;Button install,browse;Label status;ProgressBar progress;
        public Setup() {
            Text="衡策 · 安装预算分析工作台";Size=new Size(650,355);StartPosition=FormStartPosition.CenterScreen;
            FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;Font=new Font("Microsoft YaHei",10);
            var title=new Label{Text="衡策 · 智能预算分析",Font=new Font("Microsoft YaHei",20,FontStyle.Bold),AutoSize=true,Location=new Point(30,25)};
            var note=new Label{Text="安装预算分析工作台及本地知识库，无需另装开发环境。",AutoSize=true,Location=new Point(33,78)};
            location=new TextBox{Text=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","FinAgent"),Location=new Point(33,123),Width=475};
            browse=new Button{Text="选择…",Location=new Point(515,122),Size=new Size(78,30)};
            browse.Click+=(s,e)=>{using(var picker=new FolderBrowserDialog()){picker.Description="选择安装父目录，软件会放入其下的 FinAgent 文件夹";if(picker.ShowDialog()==DialogResult.OK)location.Text=Path.Combine(picker.SelectedPath,"FinAgent");}};
            progress=new ProgressBar{Location=new Point(33,173),Width=560,Height=10};
            status=new Label{Text="安装位置可修改；分析输出可在程序设置中单独指定。",Location=new Point(33,200),Width=565,Height=40};
            install=new Button{Text="安装",Location=new Point(475,255),Size=new Size(118,36)};
            install.Click+=async(s,e)=>{
                if(install.Text=="打开工作台"){Process.Start(Path.Combine(location.Text,"FinAgent.exe"));Close();return;}
                string destination=location.Text;
                install.Enabled=false;browse.Enabled=false;location.Enabled=false;status.Text="正在解压运行时与知识库…";
                try {await Task.Run(()=>Extract(destination,n=>BeginInvoke(new Action(()=>progress.Value=Math.Min(100,n)))));progress.Value=100;status.Text="安装完成。双击安装目录中的 FinAgent.exe 即可运行。";install.Text="打开工作台";}
                catch(Exception error){status.Text="安装失败："+error.Message;browse.Enabled=true;location.Enabled=true;}
                install.Enabled=true;
            };
            Controls.AddRange(new Control[]{title,note,location,browse,progress,status,install});
        }
    }
}
