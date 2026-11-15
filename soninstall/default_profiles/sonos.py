import json
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, override

from soninstall.default_profiles.desktop import DesktopProfile
from soninstall.lib.hardware import SysInfo
from soninstall.lib.pacman.pacman import Pacman
from soninstall.lib.pathnames import PACMAN_CONF

if TYPE_CHECKING:
	from soninstall.lib.installer import Installer


SONOS_PROFILE_NAME = 'sOnOs'

# The keys of the [sonos] package repository
SONOS_KEYRING = 'sonos-keyring'
# CPU, I/O and memory tuning in the style of CachyOS; pulls in ananicy-cpp, its rules and the
# sched_ext schedulers. Lives in the [sonos] repository, like the keyring.
SONOS_SETTINGS = 'sonos-settings'
# Started on the installed system when sonos-settings brought them
TUNING_SERVICES = ['ananicy-cpp', 'scx_loader']

FASTFETCH_LOGO = Path(__file__).parent / 'sonos_assets/fastfetch-logo.txt'
FASTFETCH_LOGO_TARGET = 'usr/share/sonos/fastfetch-logo.txt'

# The icon os-release names with LOGO=sonos. Without it, "About this system" pages and
# login screens fall back to the Arch Linux logo.
LOGO_ICON = Path(__file__).parent / 'sonos_assets/sonos.svg'
LOGO_ICON_TARGETS = ['usr/share/icons/hicolor/scalable/apps/sonos.svg', 'usr/share/pixmaps/sonos.svg']

# The text above the console login prompt, the name comes from os-release (Arch Linux otherwise)
ISSUE = '\\S{PRETTY_NAME} \\r (\\l)\n\n'

# The wallpapers: the first one is the default, both can be picked in the settings of the desktop
WALLPAPER_DIR = 'usr/share/backgrounds/sonos'
WALLPAPERS: dict[str, tuple[Path, str]] = {
	'sonos.jpg': (Path(__file__).parent / 'sonos_assets/wallpaper-sonos.jpg', 'sOnOs'),
	'sonos-terminal.jpg': (Path(__file__).parent / 'sonos_assets/wallpaper-sonos-terminal.jpg', 'sOnOs Terminal'),
}
DEFAULT_WALLPAPER = f'/{WALLPAPER_DIR}/sonos.jpg'

# Each desktop has its own place for the default wallpaper
# KDE Plasma: runs the scripts in this directory once for every user when the desktop starts
PLASMA_UPDATE_SCRIPT = 'usr/share/plasma/shells/org.kde.plasma.desktop/contents/updates/sonos-wallpaper.js'
PLASMA_WALLPAPER_SCRIPT = """// sOninstall: the sOnOs wallpaper on every desktop
for (const desktop of desktops()) {
	desktop.wallpaperPlugin = "org.kde.image";
	desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
	desktop.writeConfig("Image", "file:///usr/share/wallpapers/sOnOs/");
}
"""
# KDE Plasma lock screen
PLASMA_LOCK_SCREEN = """[Greeter]
WallpaperPlugin=org.kde.image

[Greeter][Wallpaper][org.kde.image][General]
Image=file:///usr/share/wallpapers/sOnOs/
"""
# GNOME, Budgie, Cinnamon and MATE: defaults for their settings; the ones of desktops
# that are not installed are skipped with a warning when the schemas are compiled
GSCHEMA_OVERRIDE = f"""[org.gnome.desktop.background]
picture-uri='file://{DEFAULT_WALLPAPER}'
picture-uri-dark='file://{DEFAULT_WALLPAPER}'
picture-options='zoom'
primary-color='#0B0909'

[org.gnome.desktop.screensaver]
picture-uri='file://{DEFAULT_WALLPAPER}'
picture-options='zoom'
primary-color='#0B0909'

[org.cinnamon.desktop.background]
picture-uri='file://{DEFAULT_WALLPAPER}'
picture-options='zoom'

[org.mate.background]
picture-filename='{DEFAULT_WALLPAPER}'
picture-options='zoom'
"""
# COSMIC: its system defaults are looked up in XDG_DATA_DIRS, where /usr/local/share comes
# before the file of the cosmic-bg package
COSMIC_BACKGROUND = 'usr/local/share/cosmic/com.system76.CosmicBackground/v1/all'
COSMIC_BACKGROUND_CONFIG = f"""(
	output: "all",
	source: Path("{DEFAULT_WALLPAPER}"),
	filter_by_theme: false,
	rotation_frequency: 3600,
	filter_method: Lanczos,
	scaling_mode: Zoom,
	sampling_method: Alphanumeric,
)
"""
# Xfce and LXQt only keep the wallpaper per user, so it is set once at the first login
WALLPAPER_AUTOSTART_SCRIPT = f"""#!/bin/sh
# sOninstall: sets the sOnOs wallpaper once for every user on Xfce and LXQt
marker="${{XDG_CONFIG_HOME:-$HOME/.config}}/sonos-wallpaper-set"
[ -e "$marker" ] && exit 0
image={DEFAULT_WALLPAPER}

case "$XDG_CURRENT_DESKTOP" in
	*XFCE*)
		# xfdesktop adds a property for every monitor and workspace once it runs
		for _ in $(seq 30); do
			properties=$(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep '/last-image$')
			[ -n "$properties" ] && break
			sleep 1
		done
		[ -z "$properties" ] && exit 0
		for property in $properties; do
			xfconf-query -c xfce4-desktop -p "$property" -s "$image"
			xfconf-query -c xfce4-desktop -p "${{property%/last-image}}/image-style" -n -t int -s 5
		done
		;;
	*LXQt*)
		sleep 3
		pcmanfm-qt --set-wallpaper="$image" --wallpaper-mode=zoom || exit 0
		;;
	*)
		exit 0
		;;
esac

mkdir -p "$(dirname "$marker")" && touch "$marker"
"""
WALLPAPER_AUTOSTART = """[Desktop Entry]
Type=Application
Name=sOnOs wallpaper
Exec=/usr/local/bin/sonos-wallpaper
OnlyShowIn=XFCE;LXQt;
NoDisplay=true
"""
# Sway: its configuration includes /etc/sway/config.d/* last
SWAY_WALLPAPER = f'output * bg {DEFAULT_WALLPAPER} fill\n'
# The Breeze theme of the SDDM login screen
SDDM_BREEZE_BACKGROUND = f'[General]\nbackground={DEFAULT_WALLPAPER}\n'

# fastfetch falls back to /etc/xdg/fastfetch when a user has no config of their own,
# so this one file covers root, existing accounts and accounts created later
FASTFETCH_CONFIG_TARGET = 'etc/xdg/fastfetch/config.jsonc'
FASTFETCH_CONFIG = {
	'logo': {
		'source': f'/{FASTFETCH_LOGO_TARGET}',
		# $1 in the logo is the red "On", $2 the rest
		'color': {'1': 'red', '2': 'white'},
	},
	'display': {'color': {'keys': 'red', 'title': 'red'}},
	# A config without a module list shows only the logo, so this is fastfetch's default list
	'modules': [
		'title',
		'separator',
		'os',
		'host',
		'kernel',
		'uptime',
		'packages',
		'shell',
		'display',
		'de',
		'wm',
		'wmtheme',
		'theme',
		'icons',
		'font',
		'cursor',
		'terminal',
		'terminalfont',
		'cpu',
		'gpu',
		'memory',
		'swap',
		'disk',
		'localip',
		'battery',
		'poweradapter',
		'locale',
		'break',
		'colors',
	],
}

OS_RELEASE = (
	'NAME="sOnOs"\n'
	'PRETTY_NAME="sOnOs"\n'
	'ID=sonos\n'
	'ID_LIKE=arch\n'
	'BUILD_ID=rolling\n'
	'ANSI_COLOR="38;2;23;147;209"\n'
	'HOME_URL="https://github.com/sOn-Os/sOnOs"\n'
	'DOCUMENTATION_URL="https://github.com/sOn-Os/sOnOs"\n'
	'SUPPORT_URL="https://github.com/sOn-Os/sOnOs"\n'
	'BUG_REPORT_URL="https://github.com/sOn-Os/sOnOs"\n'
	'PRIVACY_POLICY_URL="https://github.com/sOn-Os/sOnOs"\n'
	'LOGO="sonos"\n'
)

LSB_RELEASE = 'DISTRIB_ID="sOnOs"\nDISTRIB_RELEASE="rolling"\nDISTRIB_DESCRIPTION="sOnOs"\n'

# 64-bit Vulkan drivers; the 32-bit build of each is called lib32-<name>
VULKAN_DRIVERS = ['vulkan-radeon', 'vulkan-intel', 'vulkan-nouveau', 'nvidia-utils', 'vulkan-swrast']

# Tools installed with every sOnOs system, by category. Development tools are picked in the installer.
EXTRA_PACKAGES = [
	# Hardware and firmware tools
	'linux-firmware-marvell',
	'sof-firmware',
	'arch-install-scripts',
	'efibootmgr',
	'xdg-utils',
	'bolt',
	'alsa-utils',
	'dmidecode',
	'lsscsi',
	'mmc-utils',
	'sdparm',
	'sg3_utils',
	'usbutils',
	'usb_modeswitch',
	'usbmuxd',
	'libfido2',
	'libusb-compat',
	'pcsclite',
	'tpm2-tools',
	'openpgp-card-tools',
	# Disks, filesystems and recovery
	'bcachefs-tools',
	'btrfs-progs',
	'dosfstools',
	'e2fsprogs',
	'exfatprogs',
	'f2fs-tools',
	'fatresize',
	'fsarchiver',
	'gpart',
	'gptfdisk',
	'jfsutils',
	'lvm2',
	'mdadm',
	'dmraid',
	'smartmontools',
	'mtools',
	'nilfs-utils',
	'ntfsprogs',
	'nvme-cli',
	'partclone',
	'parted',
	'partimage',
	'squashfs-tools',
	'testdisk',
	'udftools',
	'xfsprogs',
	'ddrescue',
	'pv',
	# Networking and wireless
	'bind',
	'dhcpcd',
	'dnsmasq',
	'ethtool',
	'iw',
	'iwd',
	'linux-atm',
	'ldns',
	'modemmanager',
	'ndisc6',
	'nbd',
	'networkmanager',
	'nfs-utils',
	'nmap',
	'openconnect',
	'openssh',
	'openvpn',
	'ppp',
	'pptpclient',
	'reflector',
	'systemd-resolvconf',
	'tcpdump',
	'vpnc',
	'wireguard-tools',
	'wireless-regdb',
	'wireless_tools',
	'wpa_supplicant',
	'wvdial',
	'xl2tpd',
	'open-iscsi',
	# Virtualization
	'qemu-base',
	'qemu-guest-agent',
	'open-vm-tools',
	'virtualbox-guest-utils',
	'hyperv',
	# Command line tools, editors and terminals
	'b43-fwcutter',
	'curl',
	'darkhttpd',
	'diffutils',
	'fastfetch',
	'fd',
	'foot-terminfo',
	'ghostty-terminfo',
	'gpm',
	'hdparm',
	'htop',
	'btop',
	'irssi',
	'jq',
	'kitty-terminfo',
	'kmscon-terminfo',
	'less',
	'lftp',
	'lynx',
	'man-db',
	'man-pages',
	'mc',
	'nano',
	'neovim',
	'7zip',
	'ripgrep',
	'rsync',
	'rxvt-unicode-terminfo',
	'screen',
	'sequoia-sq',
	'terminus-font',
	'tmux',
	'tree',
	'unzip',
	'wget',
	'zip',
	'zsh',
	'git',
]


def logo_banner(columns: int) -> str:
	"""The fastfetch logo in colour, centered in a terminal that is `columns` wide"""
	white, red, reset = '\x1b[1;37m', '\x1b[1;31m', '\x1b[0m'
	lines = FASTFETCH_LOGO.read_text().splitlines()
	width = max(len(line.replace('$1', '').replace('$2', '')) for line in lines)
	indent = ' ' * max((columns - width) // 2, 0)

	return '\n'.join(f'{indent}{white}{line.replace("$1", red).replace("$2", white)}{reset}' for line in lines)


class SonosProfile(DesktopProfile):
	def __init__(self) -> None:
		super().__init__()
		self.name = SONOS_PROFILE_NAME

	@property
	@override
	def packages(self) -> list[str]:
		return list(
			dict.fromkeys(
				[
					*super().packages,
					'gamemode',
					'git',
					'micro',
					'neovim',
					'vim',
					'steam',
					'blueman',
					'fastfetch',
					'btop',
					'zsh',
					'7zip',
					'ntfs-3g',
					'brightnessctl',
					'pavucontrol',
					# No desktop profile brings a browser or a media player
					'firefox',
					'vlc',
					'vlc-plugins-all',
					'noto-fonts-emoji',
					*EXTRA_PACKAGES,
				]
			)
		)

	@override
	def install(self, install_session: Installer) -> None:
		# Steam depends on vulkan-driver and lib32-vulkan-driver. If nothing installed provides
		# them, pacman --noconfirm picks the NVIDIA packages whatever the GPU is, so the drivers
		# for this machine have to be in place before Steam is installed.
		headers = [f'{kernel}-headers' for kernel in install_session.kernels]
		install_session.add_additional_packages([*self._vulkan_packages(install_session), *headers])

		super().install(install_session)

		if language_pack := self._firefox_language_pack(install_session.target):
			install_session.add_additional_packages([language_pack])

		if self._has_sonos_repository():
			install_session.add_additional_packages([SONOS_KEYRING, SONOS_SETTINGS])

	@staticmethod
	def _has_sonos_repository() -> bool:
		"""
		The pacman.conf of the live system is copied to the target (PacmanConfig.persist), so
		a [sonos] repository in it is one the installed system keeps. Its packages are signed,
		and without the keyring the first update would fail on them.
		"""
		try:
			return re.search(r'^\[sonos\]', PACMAN_CONF.read_text(), re.MULTILINE) is not None
		except OSError:
			return False

	@staticmethod
	def _firefox_language_pack(target: Path) -> str | None:
		"""Firefox is English only, its translations are separate packages (firefox-i18n-tr, firefox-i18n-pt-br, ...)"""
		locale_conf = target / 'etc/locale.conf'
		if not locale_conf.exists():
			return None

		values = dict(line.split('=', 1) for line in locale_conf.read_text().splitlines() if '=' in line)
		# tr_TR.UTF-8, sr_RS@latin
		locale = values.get('LANG', '').strip('"').split('.')[0].split('@')[0]
		language, _, country = locale.lower().partition('_')

		if not language or language in ('c', 'en'):
			return None

		available = {line.decode().strip() for line in Pacman.run('-Ssq ^firefox-i18n-')}
		candidates = [f'firefox-i18n-{language}-{country}', f'firefox-i18n-{language}']

		return next((package for package in candidates if package in available), None)

	def _vulkan_packages(self, install_session: Installer) -> list[str]:
		installed = {line.decode().strip() for line in Pacman.run(f'-Qq --root {install_session.target}')}

		# Use the drivers that came with the selected graphics driver, otherwise detect the GPU
		drivers = [driver for driver in VULKAN_DRIVERS if driver in installed] or self._detect_vulkan_drivers()

		return [*drivers, *(f'lib32-{driver}' for driver in drivers), 'lib32-mesa']

	@staticmethod
	def _detect_vulkan_drivers() -> list[str]:
		drivers = []

		if SysInfo.has_amd_graphics():
			drivers.append('vulkan-radeon')
		if SysInfo.has_intel_graphics():
			drivers.append('vulkan-intel')
		if SysInfo.has_nvidia_graphics():
			# Works with the in-kernel nouveau driver, unlike nvidia-utils
			drivers.append('vulkan-nouveau')

		# No supported GPU (e.g. a virtual machine): fall back to the CPU-based driver
		return drivers or ['vulkan-swrast']

	@override
	def post_install(self, install_session: Installer) -> None:
		super().post_install(install_session)

		target = install_session.target

		# /etc/os-release is a symlink to /usr/lib/os-release, which the filesystem package
		# overwrites on every update. A regular /etc/os-release takes precedence, belongs to no
		# package and is left alone by systemd-tmpfiles, so the branding survives updates.
		os_release = target / 'etc/os-release'
		os_release.unlink(missing_ok=True)
		os_release.write_text(OS_RELEASE)

		# Unified kernel images embed os-release and systemd-boot takes the menu title from it.
		# The guided installer builds them once more at the end, after this branding.

		# lsb-release does not mark this file as a backup file, so keep pacman from overwriting it
		lsb_release = target / 'etc/lsb-release'
		if lsb_release.exists():
			lsb_release.write_text(LSB_RELEASE)
			self._add_no_upgrade(target / 'etc/pacman.conf', 'etc/lsb-release')

		# A backup file of the filesystem package, so updates leave it alone
		(target / 'etc/issue').write_text(ISSUE)

		for icon_target in LOGO_ICON_TARGETS:
			icon = target / icon_target
			icon.parent.mkdir(parents=True, exist_ok=True)
			LOGO_ICON.copy(icon)

		# GTK and COSMIC only find icons that are in the cache of the theme
		if (target / 'usr/bin/gtk-update-icon-cache').exists():
			install_session.arch_chroot('gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor')

		self._install_wallpapers(install_session)

		units = [target / f'usr/lib/systemd/system/{service}.service' for service in TUNING_SERVICES]
		if all(unit.exists() for unit in units):
			install_session.enable_service(TUNING_SERVICES)

		logo = target / FASTFETCH_LOGO_TARGET
		logo.parent.mkdir(parents=True, exist_ok=True)
		FASTFETCH_LOGO.copy(logo)

		fastfetch_config = target / FASTFETCH_CONFIG_TARGET
		fastfetch_config.parent.mkdir(parents=True, exist_ok=True)
		fastfetch_config.write_text(json.dumps(FASTFETCH_CONFIG, indent=2) + '\n')

	@staticmethod
	def _write(path: Path, content: str, mode: int = 0o644) -> None:
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(content)
		path.chmod(mode)

	def _install_wallpapers(self, install_session: Installer) -> None:
		target = install_session.target

		for name, (source, title) in WALLPAPERS.items():
			image = target / WALLPAPER_DIR / name
			image.parent.mkdir(parents=True, exist_ok=True)
			shutil.copyfile(source, image)

			# KDE Plasma lists wallpapers that are packages, the image itself is linked
			package = target / 'usr/share/wallpapers' / title.replace(' ', '-')
			metadata = {'KPlugin': {'Id': package.name, 'Name': title, 'License': 'GPL-3.0', 'Authors': [{'Name': 'sOnOs'}]}}
			self._write(package / 'metadata.json', json.dumps(metadata, indent=2) + '\n')
			link = package / 'contents/images/3840x2160.jpg'
			link.parent.mkdir(parents=True, exist_ok=True)
			link.unlink(missing_ok=True)
			link.symlink_to(f'/{WALLPAPER_DIR}/{name}')

		# The wallpaper pickers of GNOME and Budgie
		entries = ''.join(
			f'  <wallpaper deleted="false">\n    <name>{title}</name>\n    <filename>/{WALLPAPER_DIR}/{name}</filename>\n'
			'    <options>zoom</options>\n  </wallpaper>\n'
			for name, (_, title) in WALLPAPERS.items()
		)
		self._write(
			target / 'usr/share/gnome-background-properties/sonos.xml',
			f'<?xml version="1.0"?>\n<!DOCTYPE wallpapers SYSTEM "gnome-wp-list.dtd">\n<wallpapers>\n{entries}</wallpapers>\n',
		)

		self._write(target / PLASMA_UPDATE_SCRIPT, PLASMA_WALLPAPER_SCRIPT)
		self._write(target / 'etc/xdg/kscreenlockerrc', PLASMA_LOCK_SCREEN)

		self._write(target / 'usr/share/glib-2.0/schemas/90_sonos.gschema.override', GSCHEMA_OVERRIDE)
		if (target / 'usr/bin/glib-compile-schemas').exists():
			install_session.arch_chroot('glib-compile-schemas /usr/share/glib-2.0/schemas')

		self._write(target / COSMIC_BACKGROUND, COSMIC_BACKGROUND_CONFIG)

		self._write(target / 'usr/local/bin/sonos-wallpaper', WALLPAPER_AUTOSTART_SCRIPT, 0o755)
		self._write(target / 'etc/xdg/autostart/sonos-wallpaper.desktop', WALLPAPER_AUTOSTART)

		if (target / 'etc/sway').is_dir():
			self._write(target / 'etc/sway/config.d/50-sonos-wallpaper.conf', SWAY_WALLPAPER)

		if (target / 'usr/share/sddm/themes/breeze').is_dir():
			self._write(target / 'usr/share/sddm/themes/breeze/theme.conf.user', SDDM_BREEZE_BACKGROUND)

	@staticmethod
	def _add_no_upgrade(pacman_conf: Path, file: str) -> None:
		lines = pacman_conf.read_text().splitlines()
		entry = f'NoUpgrade = {file}'

		if entry in lines or '[options]' not in lines:
			return

		# pacman collects every NoUpgrade line, so a new line right below [options] is enough
		lines.insert(lines.index('[options]') + 1, entry)
		pacman_conf.write_text('\n'.join(lines) + '\n')
