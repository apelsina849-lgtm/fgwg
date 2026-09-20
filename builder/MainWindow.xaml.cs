using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

namespace CRPLauncher;

public partial class MainWindow : Window
{
    private enum LauncherState { NoPath, Checking, NeedInstall, Installing, Ready, Error }
    private const string ServerHost = "188.127.241.8";
    private const string ServerPort = "1154";
    private readonly string _settingsDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CRPLauncher");
    private readonly DispatcherTimer _timer;
    private LauncherState _state = LauncherState.NoPath;
    private double _target;
    private bool _busy;

    private string SettingsFile => Path.Combine(_settingsDir, "settings.json");

    public MainWindow()
    {
        InitializeComponent();
        Directory.CreateDirectory(_settingsDir);
        LoadBackground();
        LoadSettings();

        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(80) };
        _timer.Tick += (_, _) =>
        {
            if (!_busy || Progress.Value >= _target) return;
            Progress.Value = Math.Min(_target, Progress.Value + (Progress.Value < 45 ? 0.8 : 0.25));
            PercentText.Text = $"{(int)Progress.Value}%";
        };
        _timer.Start();
    }

    private sealed class SettingsModel
    {
        public string GamePath { get; set; } = "";
        public string Nickname { get; set; } = "";
    }

    private void LoadBackground()
    {
        try
        {
            if (!File.Exists(Payload.ImagePath)) return;
            var bmp = new BitmapImage();
            bmp.BeginInit();
            bmp.CacheOption = BitmapCacheOption.OnLoad;
            bmp.UriSource = new Uri(Payload.ImagePath, UriKind.Absolute);
            bmp.EndInit();
            bmp.Freeze();
            HeroImage.Source = bmp;
        }
        catch { }
    }

    private void LoadSettings()
    {
        try
        {
            if (!File.Exists(SettingsFile)) return;
            var s = JsonSerializer.Deserialize<SettingsModel>(File.ReadAllText(SettingsFile));
            if (s == null) return;
            GamePathBox.Text = s.GamePath ?? "";
            NickBox.Text = s.Nickname ?? "";
        }
        catch { }
    }

    private void SaveSettings()
    {
        try
        {
            Directory.CreateDirectory(_settingsDir);
            var s = new SettingsModel { GamePath = GamePathBox.Text.Trim(), Nickname = NickBox.Text.Trim() };
            File.WriteAllText(SettingsFile, JsonSerializer.Serialize(s, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch { }
    }

    private static bool ValidGame(string? p) =>
        !string.IsNullOrWhiteSpace(p) && File.Exists(Path.Combine(p, "gta_sa.exe"));

    private static bool MoonInstalled(string? p) =>
        ValidGame(p) && File.Exists(Path.Combine(p!, "MoonLoader.asi")) && Directory.Exists(Path.Combine(p!, "moonloader"));

    private void ProgressTo(double value, string? text = null)
    {
        Progress.Value = Math.Clamp(value, 0, 100);
        PercentText.Text = $"{(int)Progress.Value}%";
        if (!string.IsNullOrWhiteSpace(text)) StatusText.Text = text;
    }

    private void Busy(double start, double target, string text)
    {
        _busy = true;
        _target = target;
        ProgressTo(start, text);
    }

    private void SetState(LauncherState s, string? message = null)
    {
        _state = s;
        switch (s)
        {
            case LauncherState.NoPath:
                _busy = false;
                MainButton.Content = "ВЫБРАТЬ GTA";
                MainButton.IsEnabled = true;
                ProgressTo(0, message ?? "Выберите папку с gta_sa.exe");
                break;
            case LauncherState.Checking:
                MainButton.Content = "ПРОВЕРКА...";
                MainButton.IsEnabled = false;
                Busy(12, 84, message ?? "Проверяю обязательные файлы CRP...");
                break;
            case LauncherState.NeedInstall:
                _busy = false;
                MainButton.Content = "УСТАНОВИТЬ";
                MainButton.IsEnabled = true;
                ProgressTo(0, message ?? "Файлы CRP отсутствуют или повреждены. Нажмите «Установить».");
                break;
            case LauncherState.Installing:
                MainButton.Content = "УСТАНОВКА...";
                MainButton.IsEnabled = false;
                Busy(8, 92, message ?? "Устанавливаю обязательные файлы CRP...");
                break;
            case LauncherState.Ready:
                _busy = false;
                MainButton.Content = "ИГРАТЬ";
                MainButton.IsEnabled = true;
                ProgressTo(100, message ?? "Все обязательные файлы проверены ✓");
                break;
            default:
                _busy = false;
                MainButton.Content = "УСТАНОВИТЬ";
                MainButton.IsEnabled = true;
                ProgressTo(0, message ?? "Ошибка проверки. Нажмите «Установить».");
                break;
        }
    }

    private async Task<int> RunCore(string mode)
    {
        if (!File.Exists(Payload.CorePath))
            throw new FileNotFoundException("Не найден встроенный движок CRP.");

        string game = GamePathBox.Text.Trim();
        if (!ValidGame(game)) return 2;

        string report = Path.Combine(Path.GetTempPath(), $"crp-{Guid.NewGuid():N}.json");
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = Payload.CorePath,
                WorkingDirectory = Path.GetDirectoryName(Payload.CorePath)!,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            psi.ArgumentList.Add(mode == "install" ? "--install-client" : "--check-client");
            psi.ArgumentList.Add(game);
            psi.ArgumentList.Add(report);
            using var p = Process.Start(psi) ?? throw new InvalidOperationException("Не удалось запустить проверку CRP.");
            await p.WaitForExitAsync();
            return p.ExitCode;
        }
        finally
        {
            try { if (File.Exists(report)) File.Delete(report); } catch { }
        }
    }

    private async Task CheckFiles(bool play = false)
    {
        if (!ValidGame(GamePathBox.Text.Trim()))
        {
            SetState(LauncherState.NoPath, "В выбранной папке нет gta_sa.exe");
            return;
        }

        try
        {
            SetState(LauncherState.Checking);
            int code = await RunCore("check");
            if (code == 0)
            {
                SetState(LauncherState.Ready);
                if (play) StartGame();
            }
            else if (code == 2) SetState(LauncherState.NeedInstall);
            else SetState(LauncherState.Error, $"Ошибка проверки (код {code}). Нажмите «Установить».");
        }
        catch (Exception ex)
        {
            SetState(LauncherState.Error, "Ошибка проверки: " + ex.Message);
        }
    }

    private async Task InstallFiles()
    {
        if (!ValidGame(GamePathBox.Text.Trim()))
        {
            SetState(LauncherState.NoPath, "Сначала выберите папку GTA.");
            return;
        }

        try
        {
            SetState(LauncherState.Installing);
            int code = await RunCore("install");
            if (code != 0)
            {
                SetState(LauncherState.Error, $"Установка не завершена (код {code}).");
                return;
            }

            Busy(94, 98, "Установка завершена. Контрольная проверка...");
            int check = await RunCore("check");
            if (check == 0) SetState(LauncherState.Ready, "Установка завершена. Все файлы проверены ✓");
            else SetState(LauncherState.NeedInstall, "После установки часть файлов не прошла проверку.");
        }
        catch (Exception ex)
        {
            SetState(LauncherState.Error, "Ошибка установки: " + ex.Message);
        }
    }

    private void StartGame()
    {
        string game = GamePathBox.Text.Trim();
        string nick = NickBox.Text.Trim();
        if (nick.Length < 3)
        {
            MessageBox.Show("Введите ник минимум из 3 символов.", "CRP Launcher");
            return;
        }

        SaveSettings();
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = Path.Combine(game, "gta_sa.exe"),
                WorkingDirectory = game,
                UseShellExecute = true,
                Arguments = $"-c -h {ServerHost} -p {ServerPort} -n \"{nick}\""
            });
            StatusText.Text = "Игра запущена.";
        }
        catch (Exception ex)
        {
            MessageBox.Show("Не удалось запустить GTA:\n" + ex.Message, "CRP Launcher");
        }
    }

    private async Task ChooseGame()
    {
        using var dlg = new Forms.FolderBrowserDialog
        {
            Description = "Выберите папку GTA San Andreas, где находится gta_sa.exe",
            UseDescriptionForTitle = true,
            ShowNewFolderButton = false
        };
        if (dlg.ShowDialog() != Forms.DialogResult.OK) return;
        GamePathBox.Text = dlg.SelectedPath;
        SaveSettings();
        if (ValidGame(dlg.SelectedPath)) await CheckFiles();
        else SetState(LauncherState.NoPath, "В этой папке нет gta_sa.exe");
    }

    private async Task RunMoonInstaller()
    {
        string game = GamePathBox.Text.Trim();
        if (!ValidGame(game))
        {
            RefreshMoon();
            return;
        }
        if (!File.Exists(Payload.MoonInstallerPath))
        {
            MoonStatus.Text = "Статус: встроенный установщик MoonLoader не найден";
            return;
        }

        InstallMoonButton.IsEnabled = false;
        CloseModsButton.IsEnabled = false;
        MoonStatus.Text = "Статус: устанавливаю MoonLoader...";
        Busy(15, 92, "Установка MoonLoader и библиотек...");

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                UseShellExecute = false,
                CreateNoWindow = true
            };
            psi.ArgumentList.Add("-NoProfile");
            psi.ArgumentList.Add("-ExecutionPolicy");
            psi.ArgumentList.Add("Bypass");
            psi.ArgumentList.Add("-File");
            psi.ArgumentList.Add(Payload.MoonInstallerPath);
            psi.ArgumentList.Add("-GamePath");
            psi.ArgumentList.Add(game);

            using var p = Process.Start(psi) ?? throw new InvalidOperationException("Не удалось запустить установщик MoonLoader.");
            await p.WaitForExitAsync();

            _busy = false;
            if (p.ExitCode == 0 && MoonInstalled(game))
            {
                ProgressTo(100, "MoonLoader установлен ✓");
                RefreshMoon();
            }
            else
            {
                ProgressTo(0, "Не удалось установить MoonLoader");
                MoonStatus.Text = "Статус: ошибка установки. Проверьте интернет и повторите.";
            }
        }
        catch (Exception ex)
        {
            _busy = false;
            ProgressTo(0, "Не удалось установить MoonLoader");
            MoonStatus.Text = "Статус: " + ex.Message;
        }
        finally
        {
            InstallMoonButton.IsEnabled = true;
            CloseModsButton.IsEnabled = true;
        }
    }

    private void RefreshMoon()
    {
        string game = GamePathBox.Text.Trim();
        if (!ValidGame(game))
        {
            MoonStatus.Text = "Статус: сначала выберите папку GTA";
            InstallMoonButton.IsEnabled = false;
            OpenMoonFolderButton.IsEnabled = false;
        }
        else if (MoonInstalled(game))
        {
            MoonStatus.Text = "Статус: MoonLoader установлен ✓";
            InstallMoonButton.Content = "ПЕРЕУСТАНОВИТЬ MOONLOADER";
            InstallMoonButton.IsEnabled = true;
            OpenMoonFolderButton.IsEnabled = true;
        }
        else
        {
            MoonStatus.Text = "Статус: MoonLoader не установлен";
            InstallMoonButton.Content = "УСТАНОВИТЬ MOONLOADER";
            InstallMoonButton.IsEnabled = true;
            OpenMoonFolderButton.IsEnabled = false;
        }
    }

    private async void Window_Loaded(object sender, RoutedEventArgs e)
    {
        if (ValidGame(GamePathBox.Text.Trim())) await CheckFiles();
        else SetState(LauncherState.NoPath);
    }

    private void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        SaveSettings();
        _timer.Stop();
    }

    private async void MainButton_Click(object sender, RoutedEventArgs e)
    {
        if (_state == LauncherState.NoPath) await ChooseGame();
        else if (_state is LauncherState.NeedInstall or LauncherState.Error) await InstallFiles();
        else if (_state == LauncherState.Ready) await CheckFiles(true);
    }

    private async void VerifyButton_Click(object sender, RoutedEventArgs e) => await CheckFiles();
    private async void BrowseButton_Click(object sender, RoutedEventArgs e) => await ChooseGame();

    private async void GamePathBox_LostFocus(object sender, RoutedEventArgs e)
    {
        SaveSettings();
        if (ValidGame(GamePathBox.Text.Trim())) await CheckFiles();
        else SetState(LauncherState.NoPath);
    }

    private void NickBox_LostFocus(object sender, RoutedEventArgs e) => SaveSettings();

    private void ModsButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshMoon();
        ModsOverlay.Visibility = Visibility.Visible;
    }

    private void CloseModsButton_Click(object sender, RoutedEventArgs e)
    {
        if (CloseModsButton.IsEnabled) ModsOverlay.Visibility = Visibility.Collapsed;
    }

    private async void InstallMoonButton_Click(object sender, RoutedEventArgs e) => await RunMoonInstaller();

    private void OpenMoonFolderButton_Click(object sender, RoutedEventArgs e)
    {
        string path = Path.Combine(GamePathBox.Text.Trim(), "moonloader");
        if (Directory.Exists(path))
            Process.Start(new ProcessStartInfo("explorer.exe", $"\"{path}\"") { UseShellExecute = true });
    }

    private void Minimize_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
    private void Close_Click(object sender, RoutedEventArgs e) => Close();

    private void TopBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ClickCount == 2)
            WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
        else if (WindowState != WindowState.Maximized)
            DragMove();
    }
}
