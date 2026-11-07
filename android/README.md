# E-Eye Android operator shell

Local testing APK only. The app connects to the Pi interface over the same Wi-Fi hotspot, supports receipt camera/photo selection and saves CSV/capture downloads through Android's file picker. It binds its own network requests to Wi-Fi so a hotspot without internet remains usable. All WebView requests are restricted to the exact configured local Pi origin. There is no JavaScript bridge, external asset service, telemetry, or clinical calculation in this app.

## Save a session on this device

Use the result page's connected-device session download. Choose a local folder/file in Android's save picker. The app saves the ZIP, closes it, reopens the stored file, and validates the manifest checksum and every declared file's size and SHA-256. Only after this read-back succeeds does it acknowledge receipt to the original Pi. It then asks whether to remove the transferred files from the Pi; choose **Keep on Pi** to keep both copies. Pi cleanup is a separate, explicit action. Cancelled saves, failed writes, broken connections and mismatched/corrupt files never trigger acknowledgement or cleanup. A cleanup request whose response is lost is reported as unconfirmed; keep the local file and retry from the saved-file list.

**Open saved files** lists the app's verified session archives. Open one with a ZIP/file viewer, or recheck its bytes and retry Pi confirmation/cleanup. Retrying requires connecting to the original configured Pi address. Local files remain available through Android's Files app when the Pi is disconnected; the Pi cannot browse a disconnected phone. Copy saved archives to Windows for backup. Ordinary browser/legacy downloads do not acknowledge transfers and keep the Pi copy.

`ArchiveVerifier.java` is a reusable, Android-independent streaming verifier; `TransferReceiver.java` handles Android document URIs and the transfer protocol. The verifier rejects unknown/duplicate/missing entries, traversal paths, malformed manifest hashes, file-size differences and content-hash differences. Run its standalone tests with JDK 21:

```powershell
javac -d android/build/tests android/src/io/eeye/operator/ArchiveVerifier.java android/tests/ArchiveVerifierTest.java
java -cp android/build/tests io.eeye.operator.ArchiveVerifierTest
```

The SAF receive/reopen flow is compiled but still requires a physical-phone test, including full-storage, denied-permission, interrupted transfer and confirmation retry cases. Checksums verify the saved file's current readable bytes; they do not substitute for a separate Windows backup or a power-loss restoration test.

Install `output/eeye-operator-debug.apk` on an Android 8+ phone, join the laptop/Pi hotspot, enter the displayed Pi address and tap Connect. The initial address is `http://192.168.137.106:5000`. Camera access opens the phone's camera application; gallery selection opens the system document picker. Confirm OCR values in the Pi interface before saving ground truth.

Build on Windows with JDK 21 and Android API 35/build tools 35.0.0:

```powershell
.\android\build.ps1 -Sdk C:\path\to\sdk -Jdk C:\path\to\jdk
```

The build creates a local debug signing key under `android/build`. Preserve that key if you need to update the same testing installation. This key is not suitable for publishing. Google Play release requires the owner's package/signing ownership, a release build and listing/review. No Google Play publication was performed. Physical camera, hotspot reconnection, file picker and Android screen behavior require testing on the owner's phone.
