param([string]$Source=(Join-Path $PSScriptRoot 'assets\衡策Logo.png'))
$ErrorActionPreference='Stop'
$env:TEMP=Join-Path (Split-Path $PSScriptRoot -Parent) '临时'
$env:TMP=$env:TEMP
Add-Type -AssemblyName System.Drawing
$target=Join-Path $PSScriptRoot 'assets\衡策图标.ico'
$original=[Drawing.Image]::FromFile($Source)
$frames=[Collections.Generic.List[byte[]]]::new()
$sizes=@(16,24,32,48,64,128,256)
try {
 foreach($size in $sizes){
  $bitmap=[Drawing.Bitmap]::new($size,$size,[Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $graphics=[Drawing.Graphics]::FromImage($bitmap)
  $stream=[IO.MemoryStream]::new()
  try {
   $graphics.Clear([Drawing.Color]::Transparent)
   $graphics.CompositingMode=[Drawing.Drawing2D.CompositingMode]::SourceCopy
   $graphics.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
   $graphics.PixelOffsetMode=[Drawing.Drawing2D.PixelOffsetMode]::HighQuality
   $graphics.DrawImage($original,[Drawing.Rectangle]::new(0,0,$size,$size))
   $bitmap.Save($stream,[Drawing.Imaging.ImageFormat]::Png)
   $frames.Add($stream.ToArray())
  } finally {$stream.Dispose();$graphics.Dispose();$bitmap.Dispose()}
 }
} finally {$original.Dispose()}
$output=[IO.File]::Create($target);$writer=[IO.BinaryWriter]::new($output)
try {
 $writer.Write([uint16]0);$writer.Write([uint16]1);$writer.Write([uint16]$sizes.Count)
 $offset=6+16*$sizes.Count
 for($i=0;$i -lt $sizes.Count;$i++){
  $dimension=if($sizes[$i] -eq 256){0}else{$sizes[$i]}
  $writer.Write([byte]$dimension);$writer.Write([byte]$dimension);$writer.Write([byte]0);$writer.Write([byte]0)
  $writer.Write([uint16]1);$writer.Write([uint16]32);$writer.Write([uint32]$frames[$i].Length);$writer.Write([uint32]$offset)
  $offset+=$frames[$i].Length
 }
 foreach($frame in $frames){$writer.Write($frame)}
} finally {$writer.Dispose();$output.Dispose()}
$verify=[Drawing.Icon]::new($target,32,32)
try {if($verify.Width -ne 32){throw 'Windows 图标读取失败'}} finally {$verify.Dispose()}
Write-Output "图标已生成：$target（16/24/32/48/64/128/256 像素）"
