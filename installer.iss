[Setup]
AppName=Video Downloader
AppVersion=1.3.0
AppPublisher=Video Downloader
AppPublisherURL=https://github.com
DefaultDirName={autopf}\VideoDownloader
DefaultGroupName=Video Downloader
UninstallDisplayIcon={app}\VideoDownloader.exe
OutputDir=installer_output
OutputBaseFilename=VideoDownloader_Setup
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
LicenseFile=
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
french.WelcomeLabel1=Bienvenue dans l'installation de Video Downloader
french.WelcomeLabel2=Ce programme va installer Video Downloader sur votre ordinateur.%n%nVideo Downloader vous permet de telecharger des videos et de la musique depuis YouTube, SoundCloud, TikTok, Instagram et plus de 1800 sites.%n%nFonctionnalites :%n  - Telechargement video (MP4, toutes qualites)%n  - Telechargement musique (MP3, FLAC, WAV, 320kbps)%n  - Recherche par nom (YouTube, SoundCloud)%n  - Telechargement par lot et playlists%n%nCliquez sur Suivant pour continuer.
french.FinishedHeadingLabel=Installation terminee !
french.FinishedLabel=Video Downloader a ete installe avec succes.%n%nUn raccourci a ete cree sur votre Bureau.%n%nCliquez sur Terminer pour lancer l'application.

[Tasks]
Name: "desktopicon"; Description: "Creer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "startmenu"; Description: "Creer un raccourci dans le menu Demarrer"; GroupDescription: "Raccourcis :"

[Files]
Source: "dist\VideoDownloader.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Video Downloader"; Filename: "{app}\VideoDownloader.exe"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{group}\Video Downloader"; Filename: "{app}\VideoDownloader.exe"; IconFilename: "{app}\icon.ico"; Tasks: startmenu
Name: "{group}\Desinstaller Video Downloader"; Filename: "{uninstallexe}"; Tasks: startmenu

[Run]
Filename: "{app}\VideoDownloader.exe"; Description: "Lancer Video Downloader"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\downloads"
Type: filesandordirs; Name: "{app}\music"
Type: filesandordirs; Name: "{app}\ffmpeg"
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\history.json"
