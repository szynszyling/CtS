#ifndef AppVersion
  #error Pass AppVersion from the release build
#endif
#ifndef BundleHash
  #error Pass the SHA-256 of the release ZIP
#endif
#define BundleName "CtS-" + AppVersion + "-windows-x64.zip"
#define Tag "v" + AppVersion
#define Repo "szynszyling/CtS"
#define BundleUrl "https://github.com/" + Repo + "/releases/download/" + Tag + "/" + BundleName

[Setup]
AppId=CircleToSearch.Desktop
AppName=Circle to Search
AppVersion={#AppVersion}
AppPublisher=CtS
AppPublisherURL=https://github.com/{#Repo}
DefaultDirName={localappdata}\Programs\Circle to Search
DefaultGroupName=Circle to Search
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
ArchiveExtraction=full
OutputBaseFilename=CtS-{#AppVersion}-windows-x64-setup
UninstallDisplayIcon={app}\Circle to Search.exe
CloseApplications=yes
RestartApplications=no
ExtraDiskSpaceRequired=850000000
WizardStyle=modern

[Tasks]
Name: "startup"; Description: "Start Circle to Search when I sign in"; Flags: unchecked

[Files]
Source: "{tmp}\payload\Circle to Search\*"; DestDir: "{app}"; Flags: external ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal\ocr-models"

[Icons]
Name: "{group}\Circle to Search"; Filename: "{app}\Circle to Search.exe"; WorkingDir: "{app}"
Name: "{userstartup}\Circle to Search"; Filename: "{app}\Circle to Search.exe"; Parameters: "--background"; Tasks: startup

[Run]
Filename: "{app}\Circle to Search.exe"; Description: "Launch Circle to Search"; Flags: nowait postinstall skipifsilent

[Code]
var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Downloading Circle to Search',
    'Setup is downloading the application and OCR models.', nil);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Bundle, Client, TempZip: String;
  ResultCode: Integer;
begin
  Result := '';
  Bundle := ExpandConstant('{param:BUNDLE|}');
  if Bundle = '' then
    Bundle := ExpandConstant('{src}\{#BundleName}');
  TempZip := ExpandConstant('{tmp}\{#BundleName}');
  try
    if not FileExists(Bundle) then
    begin
      DownloadPage.Clear;
      DownloadPage.Add('{#BundleUrl}', '{#BundleName}', '{#BundleHash}');
      DownloadPage.Show;
      try
        try
          DownloadPage.Download;
          Bundle := TempZip;
        except
          if DownloadPage.AbortedByUser then
            RaiseException(GetExceptionMessage);
        end;
      finally
        DownloadPage.Hide;
      end;
    end;
    if not FileExists(Bundle) then
    begin
      Client := FileSearch('gh.exe', GetEnv('PATH'));
      if Client <> '' then
      begin
        WizardForm.StatusLabel.Caption := 'Downloading the GitHub release bundle...';
        if Exec(Client, 'release download {#Tag} --repo {#Repo} --pattern "{#BundleName}" --output "' +
          TempZip + '" --clobber', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and
          (ResultCode = 0) and FileExists(TempZip) then
          Bundle := TempZip;
      end;
    end;
    if not FileExists(Bundle) then
    begin
      if WizardSilent then
        RaiseException('Could not download the release bundle. Place the original ZIP next to Setup or pass /BUNDLE with its path.');
      if MsgBox('Setup could not download the bundle. Open the download in your browser, then select the downloaded ZIP here.',
        mbInformation, MB_OKCANCEL) <> IDOK then
        RaiseException('Bundle download cancelled.');
      ShellExec('open', '{#BundleUrl}', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
      Bundle := '';
      if not GetOpenFileName('Select {#BundleName} after it has downloaded', Bundle,
        ExpandConstant('{userprofile}\Downloads'), 'ZIP archives (*.zip)|*.zip', 'zip') then
        RaiseException('No release ZIP selected.');
    end;
    if CompareText(GetSHA256OfFile(Bundle), '{#BundleHash}') <> 0 then
      RaiseException('The ZIP does not match this setup version. Select the original {#BundleName} release asset.');
    ExtractArchive(Bundle, ExpandConstant('{tmp}\payload'), '', True, nil);
  except
    Result := GetExceptionMessage;
  end;
end;
