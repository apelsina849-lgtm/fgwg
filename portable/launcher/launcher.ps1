
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent $PSScriptRoot
$ManifestUrl = "https://raw.githubusercontent.com/apelsina849-lgtm/fgwg/night-protocol-portable/portable/manifest.json"
$GameHtml = Join-Path $Root "game\index.html"
$VersionFile = Join-Path $Root "version.json"

[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="NIGHT PROTOCOL Launcher — WLzar Company"
        Width="1160" Height="690" WindowStartupLocation="CenterScreen"
        Background="#030A06" Foreground="#A5D8B4" ResizeMode="CanMinimize">
  <Grid>
    <Grid.RowDefinitions><RowDefinition Height="54"/><RowDefinition Height="*"/><RowDefinition Height="42"/></Grid.RowDefinitions>
    <Border Grid.Row="0" Background="#071A11" BorderBrush="#285B3D" BorderThickness="0,0,0,1">
      <Grid Margin="22,0"><TextBlock Text="WLzar Company" FontFamily="Consolas" FontSize="18" Foreground="#9DDFB1" VerticalAlignment="Center"/>
        <TextBlock x:Name="HeaderVersion" HorizontalAlignment="Right" VerticalAlignment="Center" FontFamily="Consolas" FontSize="11" Foreground="#4C825D"/></Grid>
    </Border>

    <Grid Grid.Row="1" Margin="28,24,28,18">
      <Grid.ColumnDefinitions><ColumnDefinition Width="1.7*"/><ColumnDefinition Width="28"/><ColumnDefinition Width="1*"/></Grid.ColumnDefinitions>

      <Border Grid.Column="0" Background="#06160E" BorderBrush="#2B6643" BorderThickness="1" CornerRadius="5" Padding="12">
        <Grid Background="#020805">
          <Grid.RowDefinitions><RowDefinition Height="*"/><RowDefinition Height="34"/></Grid.RowDefinitions>
          <Grid Grid.Row="0">
            <Grid.ColumnDefinitions><ColumnDefinition Width="1*"/><ColumnDefinition Width="1*"/></Grid.ColumnDefinitions>
            <Border Grid.Column="0" Margin="20,28,10,28" Background="#071C12" BorderBrush="#306D49" BorderThickness="1" CornerRadius="4">
              <StackPanel Margin="18">
                <TextBlock Text="PERSONNEL DATABASE / OFFLINE" FontFamily="Consolas" FontSize="14" Foreground="#75B98A"/>
                <TextBlock Text="MARA VOSS" Margin="0,28,0,10" FontFamily="Consolas" FontSize="31" FontWeight="Bold" Foreground="#C4E8CD"/>
                <TextBlock Text="ID: A-104" FontFamily="Consolas" FontSize="16" Foreground="#82A88E"/>
                <TextBlock Text="DIVISION: ARCHIVE" Margin="0,8,0,0" FontFamily="Consolas" FontSize="16" Foreground="#82A88E"/>
                <TextBlock Text="PERSONNEL FILE MATCHES.&#10;BLACKOUT LOCKED SECTOR C." Margin="0,34,0,0" FontFamily="Consolas" FontSize="12" Foreground="#5C8C6C"/>
              </StackPanel>
            </Border>
            <Border Grid.Column="1" Margin="10,28,20,28" Background="#071C12" BorderBrush="#306D49" BorderThickness="1" CornerRadius="4">
              <StackPanel Margin="18">
                <TextBlock Text="INCIDENT TERMINAL" FontFamily="Consolas" FontSize="18" Foreground="#B7E5C4"/>
                <TextBlock Text="VISITOR 01 / 06" Margin="0,16,0,25" FontFamily="Consolas" FontSize="13" Foreground="#567E63"/>
                <Border BorderBrush="#2A5E3F" BorderThickness="1" Padding="11" Margin="0,5"><TextBlock Text="[1] RUN DIAGNOSTIC" FontFamily="Consolas" Foreground="#8FCDA1"/></Border>
                <Border BorderBrush="#2A5E3F" BorderThickness="1" Padding="11" Margin="0,5"><TextBlock Text="[2] AUTHORIZE ENTRY" FontFamily="Consolas" Foreground="#8FCDA1"/></Border>
                <Border BorderBrush="#2A5E3F" BorderThickness="1" Padding="11" Margin="0,5"><TextBlock Text="[3] DENY ENTRY" FontFamily="Consolas" Foreground="#8FCDA1"/></Border>
              </StackPanel>
            </Border>
          </Grid>
          <Border Grid.Row="1" Background="#04110B" BorderBrush="#173D28" BorderThickness="0,1,0,0">
            <TextBlock Text="NIGHT PROTOCOL // INCIDENT PREVIEW" FontFamily="Consolas" FontSize="10" Foreground="#47765A" VerticalAlignment="Center" Margin="12,0"/>
          </Border>
        </Grid>
      </Border>

      <StackPanel Grid.Column="2">
        <TextBlock Text="NIGHT" FontFamily="Consolas" FontSize="44" FontWeight="Bold" Foreground="#C4E9CE"/>
        <TextBlock Text="PROTOCOL" Margin="0,-10,0,0" FontFamily="Consolas" FontSize="44" FontWeight="Bold" Foreground="#C4E9CE"/>
        <TextBlock x:Name="BuildLabel" Margin="2,8,0,20" FontFamily="Consolas" FontSize="10" Foreground="#4D7C5C"/>
        <TextBlock Text="Incident-control horror.&#10;Six visitors. One sealed archive.&#10;Trust the terminal — until it lies." FontFamily="Consolas" FontSize="13" Foreground="#71927A" LineHeight="21"/>
        <Button x:Name="PlayButton" Content="PLAY" Height="48" Margin="0,30,0,7" FontFamily="Consolas" FontSize="15" Background="#0B2A19" Foreground="#C6ECD0" BorderBrush="#32714B"/>
        <Button x:Name="UpdateButton" Content="CHECK FOR UPDATE" Height="42" Margin="0,3" FontFamily="Consolas" Background="#071E13" Foreground="#91C6A0" BorderBrush="#2B6242"/>
        <Button x:Name="RepairButton" Content="REPAIR GAME FILES" Height="42" Margin="0,3" FontFamily="Consolas" Background="#071E13" Foreground="#91C6A0" BorderBrush="#2B6242"/>
        <Button x:Name="FolderButton" Content="OPEN GAME FOLDER" Height="42" Margin="0,3" FontFamily="Consolas" Background="#071E13" Foreground="#91C6A0" BorderBrush="#2B6242"/>
        <ProgressBar x:Name="Progress" Height="7" Margin="0,18,0,7" Minimum="0" Maximum="100" Value="0" Foreground="#67BD80" Background="#041008"/>
        <TextBlock x:Name="Status" Text="READY" FontFamily="Consolas" FontSize="10" Foreground="#5D946C" TextWrapping="Wrap"/>
      </StackPanel>
    </Grid>

    <Border Grid.Row="2" Background="#020704" BorderBrush="#133521" BorderThickness="0,1,0,0">
      <Grid Margin="24,0"><TextBlock Text="WLzar Company  •  NIGHT PROTOCOL update channel: ALPHA" FontFamily="Consolas" FontSize="10" Foreground="#355A42" VerticalAlignment="Center"/>
        <Button x:Name="ExitButton" Content="EXIT" HorizontalAlignment="Right" Width="90" Height="26" VerticalAlignment="Center" FontFamily="Consolas" Background="#071A11" Foreground="#6F9B7A" BorderBrush="#234F35"/>
      </Grid>
    </Border>
  </Grid>
</Window>
"@

$reader = New-Object System.Xml.XmlNodeReader $xaml
$Window = [Windows.Markup.XamlReader]::Load($reader)
$PlayButton = $Window.FindName("PlayButton")
$UpdateButton = $Window.FindName("UpdateButton")
$RepairButton = $Window.FindName("RepairButton")
$FolderButton = $Window.FindName("FolderButton")
$ExitButton = $Window.FindName("ExitButton")
$Status = $Window.FindName("Status")
$Progress = $Window.FindName("Progress")
$BuildLabel = $Window.FindName("BuildLabel")
$HeaderVersion = $Window.FindName("HeaderVersion")

function Get-LocalVersion {
    try {
        if(Test-Path $VersionFile){ return ([version]((Get-Content $VersionFile -Raw | ConvertFrom-Json).version)) }
    } catch {}
    return [version]"0.0.0"
}
function Set-Status([string]$Text){ $Status.Text = $Text; [System.Windows.Threading.Dispatcher]::CurrentDispatcher.Invoke([action]{}, "Background") }
function Safe-RelativePath([string]$p){
    if([string]::IsNullOrWhiteSpace($p) -or $p.Contains("..") -or [IO.Path]::IsPathRooted($p)){ throw "Unsafe update path" }
    return $p.Replace("/","\")
}
function Install-Manifest($Manifest){
    $UpdateButton.IsEnabled=$false; $RepairButton.IsEnabled=$false; $PlayButton.IsEnabled=$false
    $files=@($Manifest.files); $count=[Math]::Max(1,$files.Count); $i=0
    foreach($f in $files){
        $i++; $rel=Safe-RelativePath $f.path; $target=Join-Path $Root $rel
        $dir=Split-Path -Parent $target; if(!(Test-Path $dir)){New-Item -ItemType Directory -Force -Path $dir|Out-Null}
        $tmp=$target+".download"
        Set-Status ("DOWNLOADING " + $f.path + "...")
        Invoke-WebRequest -UseBasicParsing -Uri $f.url -OutFile $tmp
        Move-Item -Force $tmp $target
        $Progress.Value=[int](($i/$count)*92)
    }
    @{version=$Manifest.version;channel=$Manifest.channel}|ConvertTo-Json|Set-Content -Encoding UTF8 $VersionFile
    $Progress.Value=100; Set-Status ("UPDATED TO " + $Manifest.version + ". READY.")
    $UpdateButton.IsEnabled=$true; $RepairButton.IsEnabled=$true; $PlayButton.IsEnabled=$true
}
function Get-RemoteManifest { return Invoke-RestMethod -UseBasicParsing -Uri $ManifestUrl -TimeoutSec 12 }
function Check-Update([bool]$Install=$false,[bool]$Force=$false){
    try {
        Set-Status "CONTACTING UPDATE CHANNEL..."; $Progress.Value=8
        $m=Get-RemoteManifest; $local=Get-LocalVersion; $remote=[version]$m.version
        if($Force -or $remote -gt $local){
            if($Install -or $Force){Install-Manifest $m}
            else {Set-Status ("UPDATE " + $m.version + " AVAILABLE. PRESS CHECK FOR UPDATE TO INSTALL.");$Progress.Value=20}
        } else {Set-Status ("UP TO DATE // " + $local);$Progress.Value=0}
    } catch {Set-Status ("UPDATE SERVER UNAVAILABLE. OFFLINE PLAY STILL WORKS. " + $_.Exception.Message);$Progress.Value=0}
}
function Find-Edge {
    $candidates=@(
      "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
      "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
      "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )
    foreach($p in $candidates){if(Test-Path $p){return $p}}
    return $null
}
function Start-Game {
    if(!(Test-Path $GameHtml)){Set-Status "GAME FILE MISSING. PRESS REPAIR GAME FILES.";return}
    $uri=([uri]$GameHtml).AbsoluteUri
    $edge=Find-Edge
    if($edge){ Start-Process -FilePath $edge -ArgumentList @("--app=$uri","--start-maximized","--disable-features=msEdgeSidebarV2") }
    else { Start-Process $GameHtml }
    Set-Status "NIGHT PROTOCOL STARTED."
}

$local=Get-LocalVersion
$BuildLabel.Text="ALPHA " + $local + "  //  WINDOWS PORTABLE"
$HeaderVersion.Text="LAUNCHER 0.1.0"
$PlayButton.Add_Click({Start-Game})
$UpdateButton.Add_Click({Check-Update $true $false})
$RepairButton.Add_Click({Check-Update $true $true})
$FolderButton.Add_Click({Start-Process explorer.exe $Root})
$ExitButton.Add_Click({$Window.Close()})
$Window.Add_ContentRendered({Check-Update $false $false})
$null=$Window.ShowDialog()
