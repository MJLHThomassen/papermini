; Inno Setup script: the Windows installer of papermini (https://jrsoftware.org/isinfo.php).
;
;   python scripts/build_installer.py      (finds ISCC and passes the defines below)
;
; Installs the PyInstaller build (dist\papermini) for the current user, in
; %LocalAppData%\Programs\papermini, without asking for administrator rights, so the
; app can update itself: an installed papermini updates by running the installer of
; the new version silently (see papermini.update). The uninstaller offers to delete
; papermini's cache (downloaded models, masks and images).
;
; Defines (iscc /DName=value):
;   AppVersion           the version shown in Apps & features (required)
;   SourceDir            the PyInstaller build to install (default ..\dist\papermini)
;   OutputDir            where the installer is written (default ..\dist)
;   OutputBaseFilename   its file name without .exe (default papermini-setup)

#ifndef AppVersion
  #error Pass the version: iscc /DAppVersion=1.2.3 packaging\papermini.iss
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\papermini"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef OutputBaseFilename
  #define OutputBaseFilename "papermini-setup"
#endif

[Setup]
; the one identity of papermini's installs: a newer installer upgrades the same install,
; and papermini finds its entry in Apps & features by it (papermini.update.SETUP_KEY)
AppId={{8ABD2E9A-F789-4350-88F8-2565C60699F0}
AppName=papermini
AppVersion={#AppVersion}
AppVerName=papermini {#AppVersion}
AppPublisher=Maarten Thomassen
AppPublisherURL=https://github.com/MJLHThomassen/papermini
AppSupportURL=https://github.com/MJLHThomassen/papermini/issues
AppUpdatesURL=https://github.com/MJLHThomassen/papermini/releases
; per user: no administrator rights, and the app may replace itself when it updates
PrivilegesRequired=lowest
DefaultDirName={autopf}\papermini
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\papermini.exe
UninstallDisplayName=papermini
SetupIconFile=icon.ico
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; the PATH task changes the user's environment: tell running programs (Explorer)
ChangesEnvironment=yes
Compression=lzma2/max
SolidCompression=yes
SourceDir=.
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "path"; Description: "Add papermini to PATH, to use its command line in a terminal"; GroupDescription: "Command line:"; Flags: unchecked

[InstallDelete]
; the files of the version being replaced (an update may drop or rename some)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\papermini"; Filename: "{app}\papermini.exe"
Name: "{autodesktop}\papermini"; Filename: "{app}\papermini.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\papermini.exe"; Description: "{cm:LaunchProgram,papermini}"; Flags: nowait postinstall skipifsilent

[Code]
const
  EnvKey = 'Environment';

{ PATH: the task adds the app folder to the user's PATH; the uninstaller removes it }

function PathHas(Path, Dir: string): Integer;
begin
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';');
end;

procedure AddToPath(Dir: string);
var
  Path: string;
begin
  if not RegQueryStringValue(HKCU, EnvKey, 'Path', Path) then
    Path := '';
  if PathHas(Path, Dir) > 0 then
    exit;
  if (Path <> '') and (Copy(Path, Length(Path), 1) <> ';') then
    Path := Path + ';';
  RegWriteExpandStringValue(HKCU, EnvKey, 'Path', Path + Dir);
end;

procedure RemoveFromPath(Dir: string);
var
  Path: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKCU, EnvKey, 'Path', Path) then
    exit;
  P := PathHas(Path, Dir);
  if P = 0 then
    exit;
  Path := ';' + Path + ';';
  Delete(Path, P, Length(Dir) + 1);  { (";Dir", keeping the separator after it) }
  RegWriteExpandStringValue(HKCU, EnvKey, 'Path', Copy(Path, 2, Length(Path) - 2));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('path') then
    AddToPath(ExpandConstant('{app}'));
end;

{ The cache: papermini keeps downloaded models, masks and images in
  %PAPERMINI_CACHE% or %USERPROFILE%\.cache\papermini; the uninstaller asks whether
  to delete it (not when it runs silently) }

function CacheDir: string;
begin
  Result := GetEnv('PAPERMINI_CACHE');
  if Result = '' then
    Result := ExpandConstant('{%USERPROFILE}\.cache\papermini');
end;

function FolderSize(Dir: string): Int64;
var
  F: TFindRec;
begin
  Result := 0;
  if FindFirst(AddBackslash(Dir) + '*', F) then
  try
    repeat
      if (F.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
      begin
        if (F.Name <> '.') and (F.Name <> '..') and
           ((F.Attributes and FILE_ATTRIBUTE_REPARSE_POINT) = 0) then
          Result := Result + FolderSize(AddBackslash(Dir) + F.Name);
      end
      else
        Result := Result + Int64(F.SizeHigh) * 4294967296 + F.SizeLow;
    until not FindNext(F);
  finally
    FindClose(F);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Dir: string;
begin
  if CurUninstallStep = usUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    Dir := CacheDir;
    if DirExists(Dir) and
       (MsgBox('Also delete papermini''s downloaded models and other cached files ('
               + IntToStr(FolderSize(Dir) div 1048576) + ' MB)?' + #13#10#13#10
               + Dir + #13#10#13#10
               + 'Keep them if you will install papermini again, so the models need '
               + 'not be downloaded again.',
               mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(Dir, True, True, True);
  end;
end;
