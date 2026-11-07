# E-Eye Android operator shell

Local testing APK only. The app connects to the Pi interface over the same Wi-Fi hotspot, supports receipt camera/photo selection and saves CSV/capture downloads through Android's file picker. It binds its own network requests to Wi-Fi so a hotspot without internet remains usable. All WebView requests are restricted to the exact configured local Pi origin. There is no JavaScript bridge, external asset service, telemetry, or clinical calculation in this app.

Install `output/eeye-operator-debug.apk` on an Android 8+ phone, join the laptop/Pi hotspot, enter the displayed Pi address and tap Connect. The initial address is `http://192.168.137.106:5000`. Camera access opens the phone's camera application; gallery selection opens the system document picker. Confirm OCR values in the Pi interface before saving ground truth.

Build on Windows with JDK 21 and Android API 35/build tools 35.0.0:

```powershell
.\android\build.ps1 -Sdk C:\path\to\sdk -Jdk C:\path\to\jdk
```

The build creates a local debug signing key under `android/build`. Preserve that key if you need to update the same testing installation. This key is not suitable for publishing. Google Play release requires the owner's package/signing ownership, a release build and listing/review. No Google Play publication was performed. Physical camera, hotspot reconnection, file picker and Android screen behavior require testing on the owner's phone.
