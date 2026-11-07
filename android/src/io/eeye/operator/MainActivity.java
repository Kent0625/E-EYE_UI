package io.eeye.operator;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.provider.Settings;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private WebView web;
    private EditText address;
    private TextView status;
    private Uri origin, cameraUri;
    private ValueCallback<Uri[]> fileCallback;
    private String downloadUrl;
    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback networkCallback;
    private boolean loadFailed;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);
        root.setPadding(dp(12), dp(8), dp(12), 0);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(dp(12), insets.getSystemWindowInsetTop()+dp(8), dp(12), insets.getSystemWindowInsetBottom());
            return insets;
        });
        address = new EditText(this);
        address.setSingleLine(true);
        address.setHint("Pi address");
        address.setContentDescription("Raspberry Pi address");
        address.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        address.setText(getPreferences(0).getString("address", "http://192.168.137.106:5000"));
        root.addView(address);
        LinearLayout controls = new LinearLayout(this);
        addButton(controls, "Connect", view -> connect());
        addButton(controls, "Reload", view -> { if (origin != null) web.reload(); });
        addButton(controls, "Open Wi-Fi", view -> startActivity(new Intent(Settings.ACTION_WIFI_SETTINGS)));
        root.addView(controls);
        LinearLayout files = new LinearLayout(this);
        addButton(files, "Open saved files", view -> showSavedFiles());
        root.addView(files);
        status = new TextView(this);
        status.setText("Join the same hotspot as the Pi, then connect.");
        status.setPadding(0, dp(4), 0, dp(8));
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        root.addView(status);
        web = new WebView(this);
        root.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
        configureWeb();
        connectivity = (ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) {
                connectivity.bindProcessToNetwork(network);
            }
            @Override public void onLost(Network network) {
                runOnUiThread(() -> showStatus("Wi-Fi disconnected. Rejoin the hotspot and reload."));
            }
        };
        connectivity.registerNetworkCallback(new NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build(), networkCallback);
        for (Network network : connectivity.getAllNetworks()) {
            NetworkCapabilities caps = connectivity.getNetworkCapabilities(network);
            if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) connectivity.bindProcessToNetwork(network);
        }
        connect();
    }

    private int dp(int pixels) { return Math.round(pixels * getResources().getDisplayMetrics().density); }
    private void addButton(LinearLayout row, String text, View.OnClickListener click) {
        Button button = new Button(this); button.setText(text); button.setOnClickListener(click);
        row.addView(button, new LinearLayout.LayoutParams(0, dp(48), 1));
    }
    private void showStatus(String text) { status.setText(text); }
    private boolean localAddress(Uri uri) {
        String host = uri.getHost();
        if (host == null || uri.getUserInfo() != null || !"http".equals(uri.getScheme()) || uri.getFragment()!=null || uri.getQuery()!=null) return false;
        if ("eeye.local".equalsIgnoreCase(host) || "eeye.mshome.net".equalsIgnoreCase(host)) return true;
        String[] parts = host.split("\\.");
        if (parts.length != 4) return false;
        int[] ip = new int[4];
        try { for (int i=0;i<4;i++) { ip[i]=Integer.parseInt(parts[i]); if(ip[i]<0 || ip[i]>255) return false; } }
        catch (NumberFormatException error) { return false; }
        return ip[0]==10 || (ip[0]==192 && ip[1]==168) || (ip[0]==172 && ip[1]>=16 && ip[1]<=31);
    }
    private void connect() {
        Uri candidate = Uri.parse(address.getText().toString().trim());
        if (!localAddress(candidate) || !(candidate.getPath()==null || candidate.getPath().isEmpty() || "/".equals(candidate.getPath()))) {
            showStatus("Enter a local Pi address, for example http://192.168.137.106:5000."); return;
        }
        origin = candidate.buildUpon().path("").build();
        getPreferences(0).edit().putString("address",origin.toString()).apply();
        showStatus("Connecting to the Pi…");
        web.loadUrl(origin.toString()+"/");
    }
    private int port(Uri uri) { return uri.getPort()<0 ? 80 : uri.getPort(); }
    private boolean permitted(Uri uri) {
        return origin != null && "http".equals(uri.getScheme()) && uri.getUserInfo()==null
            && origin.getHost().equalsIgnoreCase(uri.getHost()) && port(origin)==port(uri);
    }
    private void configureWeb() {
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                loadFailed=false;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (!permitted(request.getUrl())) { showStatus("This app opens only the configured Pi."); return true; }
                return false;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (permitted(request.getUrl())) return null;
                return new WebResourceResponse("text/plain","UTF-8",403,"Blocked",null,new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) { loadFailed=true; showStatus("Pi unavailable. Check its power and hotspot connection, then reload."); }
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!loadFailed && permitted(Uri.parse(url)) && view.getProgress()==100) showStatus("Pi interface: "+origin.getHost());
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (origin==null || !permitted(Uri.parse(view.getUrl()))) return false;
                if (fileCallback!=null) fileCallback.onReceiveValue(null);
                fileCallback=callback;
                Intent gallery=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE);
                cameraUri=Uri.parse("content://io.eeye.operator.receipt/receipt-"+UUID.randomUUID()+".jpg");
                Intent camera=new Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT,cameraUri);
                camera.setClipData(ClipData.newRawUri("Receipt photo",cameraUri));
                camera.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                Intent chooser=Intent.createChooser(gallery,"Attach receipt");
                if(camera.resolveActivity(getPackageManager())!=null) chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS,new Intent[]{camera});
                try { startActivityForResult(chooser,10); }
                catch (android.content.ActivityNotFoundException error) { fileCallback.onReceiveValue(null); fileCallback=null; showStatus("No image picker is installed. Use the phone browser to attach a receipt."); }
                return true;
            }
        });
        web.setDownloadListener((url,agent,disposition,type,length)->{
            if(!permitted(Uri.parse(url))) return;
            downloadUrl=url;
            boolean transfer=isTransfer(url);
            String name=transfer?"eeye-session-"+Uri.parse(url).getPathSegments().get(2)+".zip":url.contains("export.csv")?"eeye-records.csv":"eeye-capture.zip";
            Intent create=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType(url.contains("export.csv")?"text/csv":"application/zip").putExtra(Intent.EXTRA_TITLE,name)
                .putExtra(Intent.EXTRA_LOCAL_ONLY,true);
            startActivityForResult(create,11);
        });
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==10 && fileCallback!=null) {
            Uri selected = result==RESULT_OK ? (data!=null && data.getData()!=null ? data.getData() : cameraUri) : null;
            fileCallback.onReceiveValue(selected==null?null:new Uri[]{selected}); fileCallback=null;
            if(cameraUri!=null) revokeUriPermission(cameraUri,Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_READ_URI_PERMISSION);
        }
        if(request==11) {
            if(result==RESULT_OK && data!=null && data.getData()!=null) {
                Uri destination=data.getData();
                try {getContentResolver().takePersistableUriPermission(destination,data.getFlags()&(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION));}
                catch(SecurityException ignored) {}
                saveDownload(destination);
            } else if(isTransfer(downloadUrl)) showStatus("Save cancelled. The Pi keeps its files.");
        }
    }
    private boolean isTransfer(String url) {
        return url!=null && Uri.parse(url).getPath()!=null && Uri.parse(url).getPath().matches("/api/transfers/[0-9a-f]{32}/archive");
    }
    private void onUi(Runnable action) {runOnUiThread(()->{if(!isFinishing() && !isDestroyed())action.run();});}
    private void saveDownload(Uri destination) {
        final String selected=downloadUrl;
        if(selected==null || !permitted(Uri.parse(selected))) return;
        if(isTransfer(selected)) {saveTransfer(destination,selected);return;}
        showStatus("Saving file from the Pi…");
        new Thread(()->{
            HttpURLConnection connection=null;
            try {
                connection=(HttpURLConnection)new URL(selected).openConnection();
                connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(10000); connection.setReadTimeout(30000);
                String cookie=CookieManager.getInstance().getCookie(selected); if(cookie!=null) connection.setRequestProperty("Cookie",cookie);
                if(connection.getResponseCode()!=200) throw new java.io.IOException("Download failed");
                try(InputStream input=connection.getInputStream();OutputStream output=getContentResolver().openOutputStream(destination,"w")) {
                    byte[] buffer=new byte[65536]; int count;
                    while((count=input.read(buffer))!=-1) output.write(buffer,0,count);
                }
                runOnUiThread(()->showStatus("File saved."));
            } catch(Exception error) { runOnUiThread(()->showStatus("File was not fully saved. Reconnect to the Pi and retry.")); }
            finally { if(connection!=null) connection.disconnect(); }
        },"eeye-download").start();
    }
    private void saveTransfer(Uri destination,String selected) {
        final String cookie=CookieManager.getInstance().getCookie(selected);
        showStatus("Saving session. The Pi keeps its copy until the saved file is checked.");
        new Thread(()->{
            try {
                TransferReceiver receiver=new TransferReceiver(getContentResolver(),cookie);
                TransferReceiver.Saved saved=receiver.receive(destination,selected);
                rememberSaved(saved);
                onUi(()->showStatus("Session saved and checked. Confirming receipt with the Pi…"));
                try {receiver.acknowledge(saved);}
                catch(Exception error) {onUi(()->showStatus("File saved and checked. The Pi copy is kept. Open saved files to retry confirmation."));return;}
                onUi(()->askRelease(saved));
            } catch(Exception error) {
                onUi(()->showStatus("Session was not fully saved and checked. The Pi keeps its files. Choose a local folder with space and retry."));
            }
        },"eeye-verified-save").start();
    }
    private synchronized void rememberSaved(TransferReceiver.Saved saved)throws Exception {
        JSONArray records=new JSONArray(getPreferences(0).getString("saved_files","[]"));
        for(int i=0;i<records.length();i++)if(records.getJSONObject(i).getString("uri").equals(saved.uri.toString()))return;
        records.put(saved.record());
        if(!getPreferences(0).edit().putString("saved_files",records.toString()).commit())throw new java.io.IOException("Could not remember the saved session");
    }
    private void askRelease(TransferReceiver.Saved saved) {
        showStatus("Session saved and checked. Pi copy kept until you choose Remove from Pi.");
        new AlertDialog.Builder(this).setTitle("Session saved and checked")
            .setMessage("Remove the transferred capture and receipt files from the Pi? Keep this saved archive and copy it to your Windows backup.")
            .setNegativeButton("Keep on Pi",(dialog,which)->showStatus("Session saved. The Pi copy is kept."))
            .setPositiveButton("Remove from Pi",(dialog,which)->releaseSaved(saved)).show();
    }
    private void releaseSaved(TransferReceiver.Saved saved) {
        if(!permitted(Uri.parse(saved.url))){showStatus("Connect to the original Pi address before releasing its files.");return;}
        showStatus("Checking the saved file again before requesting Pi cleanup…");
        final String cookie=CookieManager.getInstance().getCookie(saved.url);
        new Thread(()->{
            try {
                TransferReceiver receiver=new TransferReceiver(getContentResolver(),cookie);
                TransferReceiver.Saved checked=receiver.readBack(saved.uri,saved.url,saved.manifestHash,saved.archiveHash,saved.archiveBytes);
                receiver.acknowledge(checked);
                receiver.release(checked);
                onUi(()->{
                    showStatus("The Pi confirmed cleanup. Session files are saved on this device.");
                    if(web.getUrl()!=null && permitted(Uri.parse(web.getUrl())))web.reload();
                });
            }catch(Exception error){onUi(()->showStatus("Pi cleanup was not confirmed. Keep the saved file and check the transfer status before retrying."));}
        },"eeye-release").start();
    }
    private void showSavedFiles() {
        try {
            JSONArray records=new JSONArray(getPreferences(0).getString("saved_files","[]"));
            if(records.length()==0){showStatus("No verified session files saved by this app yet.");return;}
            String[] names=new String[records.length()];
            for(int i=0;i<names.length;i++)names[i]=records.getJSONObject(i).getString("participant_code")+" · "+(i+1);
            new AlertDialog.Builder(this).setTitle("Saved session files").setItems(names,(dialog,index)->{
                try {savedFileActions(records.getJSONObject(index));}catch(Exception error){showStatus("Saved-file information could not be read.");}
            }).setNegativeButton("Close",null).show();
        }catch(Exception error){showStatus("The saved-file list could not be read. Use the phone Files app to find your archives.");}
    }
    private void savedFileActions(JSONObject record)throws Exception {
        Uri uri=Uri.parse(record.getString("uri"));String url=record.getString("url"),hash=record.getString("manifest_sha256"),archiveHash=record.getString("archive_sha256");long archiveBytes=record.getLong("archive_bytes");
        new AlertDialog.Builder(this).setTitle(record.getString("participant_code"))
            .setItems(new String[]{"Open saved archive","Verify file and retry Pi confirmation"},(dialog,index)->{
                if(index==0){
                    Intent open=new Intent(Intent.ACTION_VIEW).setDataAndType(uri,"application/zip").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    try{startActivity(open);}catch(Exception error){showStatus("No archive viewer can open this file. Use the phone Files app.");}
                }else{
                    if(!permitted(Uri.parse(url))){showStatus("Connect to the original Pi address before confirming this saved file.");return;}
                    showStatus("Reopening and checking every saved file…");
                    final String cookie=CookieManager.getInstance().getCookie(url);
                    new Thread(()->{
                        try{
                            TransferReceiver receiver=new TransferReceiver(getContentResolver(),cookie);
                            TransferReceiver.Saved saved=receiver.readBack(uri,url,hash,archiveHash,archiveBytes);
                            receiver.acknowledge(saved);
                            onUi(()->askRelease(saved));
                        }catch(Exception error){onUi(()->showStatus("Saved file could not be verified or confirmed. The app has not requested Pi cleanup."));}
                    },"eeye-recheck").start();
                }
            }).setNegativeButton("Cancel",null).show();
    }
    @Override public void onBackPressed() { if(web.canGoBack()) web.goBack(); else super.onBackPressed(); }
    @Override protected void onDestroy() {
        if(fileCallback!=null) fileCallback.onReceiveValue(null);
        if(connectivity!=null && networkCallback!=null) connectivity.unregisterNetworkCallback(networkCallback);
        if(web!=null) web.destroy();
        super.onDestroy();
    }
}
