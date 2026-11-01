# Caelum 0.3.3

Fixes global dictation shortcuts in native packages, including Ctrl + Super on Hyprland. Shortcut commands now carry Caelum’s library path explicitly instead of relying on the compositor to inherit the daemon’s environment.

Releases now provide packages for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43. Release downloads contain the four packages plus signed update metadata; Debian packages, per-package checksum files, and the Arch source recipe are no longer uploaded.

Package verification continues to use the signed SHA-256 digests in update.json. The signing key, exact distribution/version checks, and update signature verification are unchanged.

Settings, keys, and history are retained when upgrading.
