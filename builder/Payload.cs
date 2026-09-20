using System;
using System.IO;

namespace CRPLauncher;

internal static class Payload
{
    public static string BaseDir { get; } = AppContext.BaseDirectory;
    public static string CorePath => Path.Combine(BaseDir, "Core", "CRP Launcher Core.exe");
    public static string ImagePath => Path.Combine(BaseDir, "Assets", "loading.png");
    public static string IconPath => Path.Combine(BaseDir, "CRP Launcher.ico");
    public static string MoonInstallerPath => Path.Combine(BaseDir, "Tools", "install-moonloader.ps1");
}
