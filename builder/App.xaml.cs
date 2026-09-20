using System;
using System.Windows;

namespace CRPLauncher;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            Payload.EnsureExtracted();
        }
        catch (Exception ex)
        {
            MessageBox.Show("Не удалось подготовить встроенные файлы лаунчера:\n" + ex.Message,
                "CRP Launcher", MessageBoxButton.OK, MessageBoxImage.Error);
        }

        var window = new MainWindow();
        MainWindow = window;
        window.Show();
    }
}
