param([string]$Sdk, [string]$Jdk)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot
if (!$Sdk) { $Sdk = Join-Path $project 'output/toolchain/sdk' }
if (!$Jdk) { $Jdk = (Get-ChildItem (Join-Path $project 'output/toolchain/jdk') -Directory | Select-Object -First 1).FullName }
$env:JAVA_HOME = $Jdk
$env:PATH = "$Jdk\bin;$env:PATH"
$tools = Join-Path $Sdk 'build-tools/35.0.0'
$platform = Join-Path $Sdk 'platforms/android-35/android.jar'
$build = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $build,(Join-Path $build 'classes'),(Join-Path $build 'generated'),(Join-Path $build 'dex') | Out-Null
function Run([scriptblock]$command) { & $command; if ($LASTEXITCODE -ne 0) { throw "Build command failed: $command" } }
Run { & "$tools/aapt2.exe" compile --dir "$PSScriptRoot/res" -o "$build/resources.zip" }
Run { & "$tools/aapt2.exe" link -o "$build/base.apk" -I $platform --manifest "$PSScriptRoot/AndroidManifest.xml" --java "$build/generated" "$build/resources.zip" }
$sources = @(Get-ChildItem "$PSScriptRoot/src" -Filter '*.java' -Recurse | Select-Object -ExpandProperty FullName)
Run { & "$Jdk/bin/javac.exe" -source 8 -target 8 -classpath $platform -d "$build/classes" $sources }
Run { & "$Jdk/bin/jar.exe" cf "$build/classes.jar" -C "$build/classes" . }
Run { & "$tools/d8.bat" --min-api 26 --lib $platform --output "$build/dex" "$build/classes.jar" }
Copy-Item "$build/base.apk" "$build/unsigned.apk" -Force
Run { & "$Jdk/bin/jar.exe" uf "$build/unsigned.apk" -C "$build/dex" classes.dex }
Run { & "$tools/zipalign.exe" -f 4 "$build/unsigned.apk" "$build/aligned.apk" }
$key = Join-Path $build 'debug.keystore'
if (!(Test-Path $key)) { Run { & "$Jdk/bin/keytool.exe" -genkeypair -keystore $key -storepass android -keypass android -alias androiddebugkey -dname 'CN=E-Eye Local Development' -keyalg RSA -keysize 2048 -validity 3650 } }
$apk = Join-Path $project 'output/eeye-operator-debug.apk'
Run { & "$tools/apksigner.bat" sign --ks $key --ks-pass pass:android --key-pass pass:android --out $apk "$build/aligned.apk" }
Run { & "$tools/apksigner.bat" verify --verbose $apk }
Get-FileHash $apk -Algorithm SHA256
