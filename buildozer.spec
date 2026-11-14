[app]
title = Restart DPD
package.name = restartdpd
package.domain = org.restart

source.dir = .
source.include_exts = py,png,jpg,kv,json

version = 1.0
requirements = python3,kivy==2.3.0,pymysql

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
