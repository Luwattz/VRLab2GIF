# The layout suite checks normal and 200% text on a full desktop. Hosted
# runners otherwise use 1024x768, which cannot fit the intended test windows.
$ErrorActionPreference = "Stop"
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class CiDisplay {
    // DEVMODEW is 220 bytes; retain all fields returned by Windows and change
    // only dmPelsWidth/dmPelsHeight. No persistent registry settings are saved.
    [StructLayout(LayoutKind.Explicit, Size=220)]
    public struct Mode {
        [FieldOffset(68)] public ushort Size;
        [FieldOffset(72)] public uint Fields;
        [FieldOffset(172)] public uint Width;
        [FieldOffset(176)] public uint Height;
    }
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern bool EnumDisplaySettings(string device, int mode, ref Mode data);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern int ChangeDisplaySettings(ref Mode data, uint flags);
}
'@
$mode = New-Object CiDisplay+Mode
$mode.Size = 220
if (-not [CiDisplay]::EnumDisplaySettings($null, -1, [ref]$mode)) {
    throw "Cannot read the CI desktop mode."
}
$mode.Width = 1920
$mode.Height = 1080
$mode.Fields = $mode.Fields -bor 0x180000
$result = [CiDisplay]::ChangeDisplaySettings([ref]$mode, 0)
if ($result -ne 0) { throw "Cannot configure the CI desktop: $result" }
Write-Host "CI desktop configured to 1920x1080."
