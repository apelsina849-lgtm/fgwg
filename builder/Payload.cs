using System;
using System.IO;
using System.Text;

namespace CRPLauncher;

internal static class Payload
{
    private const string Magic = "CRP_PAYLOAD_V1!!";
    private const int FooterSize = 16 + 8 + 8 + 8;

    public static string BaseDir { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "CRPLauncher", "embedded-v1");

    public static string CorePath => Path.Combine(BaseDir, "CRP Launcher Core.exe");
    public static string ImagePath => Path.Combine(BaseDir, "loading.png");
    public static string MoonInstallerPath => Path.Combine(BaseDir, "install-moonloader.ps1");

    public static void EnsureExtracted()
    {
        Directory.CreateDirectory(BaseDir);
        var self = Environment.ProcessPath ?? throw new InvalidOperationException("Не удалось определить путь к лаунчеру.");

        using var fs = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (fs.Length < FooterSize)
            throw new InvalidDataException("В EXE отсутствует встроенный пакет CRP.");

        fs.Seek(-FooterSize, SeekOrigin.End);
        using var br = new BinaryReader(fs, Encoding.ASCII, leaveOpen: true);
        var magic = Encoding.ASCII.GetString(br.ReadBytes(16));
        if (magic != Magic)
            throw new InvalidDataException("Встроенный пакет CRP не найден. Скачайте полный CRP Launcher.exe.");

        long coreLength = br.ReadInt64();
        long imageLength = br.ReadInt64();
        long scriptLength = br.ReadInt64();
        long payloadStart = fs.Length - FooterSize - coreLength - imageLength - scriptLength;
        if (coreLength <= 0 || imageLength <= 0 || scriptLength <= 0 || payloadStart < 0)
            throw new InvalidDataException("Встроенный пакет CRP повреждён.");

        ExtractPart(fs, payloadStart, coreLength, CorePath);
        ExtractPart(fs, payloadStart + coreLength, imageLength, ImagePath);
        ExtractPart(fs, payloadStart + coreLength + imageLength, scriptLength, MoonInstallerPath);
    }

    private static void ExtractPart(FileStream fs, long offset, long length, string destination)
    {
        if (File.Exists(destination) && new FileInfo(destination).Length == length)
            return;

        var tmp = destination + ".tmp";
        fs.Seek(offset, SeekOrigin.Begin);
        using (var output = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            byte[] buffer = new byte[1024 * 1024];
            long remaining = length;
            while (remaining > 0)
            {
                int read = fs.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                if (read <= 0) throw new EndOfStreamException("Встроенный пакет CRP обрезан.");
                output.Write(buffer, 0, read);
                remaining -= read;
            }
        }

        File.Move(tmp, destination, true);
    }
}
