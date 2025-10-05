[app]
title = PingGroups
package.name = pinggroups
package.domain = org.example
version = 0.1.0

source.dir = .
source.include_exts = py,kv,png,jpg,atlas
source.exclude_dirs = venv, .git, bin, __pycache__

requirements = python3,kivy==2.3.0,plyer,requests

orientation = portrait
fullscreen = 0

[android]
android.api = 34
android.minapi = 24
android.permissions = INTERNET,VIBRATE,POST_NOTIFICATIONS
android.archs = arm64-v8a
android.enable_androidx = True
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
build_dir = /home/user/.buildozer
bin_dir = /home/user/app/bin