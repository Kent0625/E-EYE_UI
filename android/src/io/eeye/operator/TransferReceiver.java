package io.eeye.operator;

import android.content.ContentResolver;
import android.net.Uri;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.IOException;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/** Saves a transfer and proves its read-back bytes before acknowledging it. */
public final class TransferReceiver {
    public static final class Saved {
        public final Uri uri;
        public final String url, manifestHash;
        public final JSONObject manifest;
        Saved(Uri uri,String url,String hash,JSONObject manifest) {this.uri=uri;this.url=url;this.manifestHash=hash;this.manifest=manifest;}
        public JSONObject record()throws Exception {
            return new JSONObject().put("uri",uri.toString()).put("url",url).put("manifest_sha256",manifestHash)
                .put("participant_code",manifest.getString("participant_code"));
        }
    }
    private final ContentResolver resolver;
    private final String cookie;
    public TransferReceiver(ContentResolver resolver,String cookie) {this.resolver=resolver;this.cookie=cookie;}
    private static URL archiveUrl(String value)throws IOException {
        URL url=new URL(value);
        if(!"http".equals(url.getProtocol()) || url.getUserInfo()!=null || url.getQuery()!=null || url.getRef()!=null
            || !url.getPath().matches("/api/transfers/[0-9a-f]{32}/archive"))throw new IOException("Invalid transfer address");
        return url;
    }
    private HttpURLConnection open(URL url)throws IOException {
        HttpURLConnection connection=(HttpURLConnection)url.openConnection();
        connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(10000);connection.setReadTimeout(30000);
        if(cookie!=null)connection.setRequestProperty("Cookie",cookie);
        return connection;
    }
    public Saved receive(Uri destination,String address)throws Exception {
        URL url=archiveUrl(address);HttpURLConnection connection=open(url);
        String expected;
        try {
            if(connection.getResponseCode()!=200)throw new IOException("The Pi could not provide this transfer");
            expected=connection.getHeaderField("X-EEye-Manifest-SHA256");
            if(!ArchiveVerifier.validHash(expected))throw new IOException("The Pi did not provide a valid manifest checksum");
            long total=0,length=connection.getContentLengthLong();
            try(InputStream input=connection.getInputStream();OutputStream output=resolver.openOutputStream(destination,"w")) {
                if(output==null)throw new IOException("The selected file cannot be written");
                byte[] buffer=new byte[65536];int count;
                while((count=input.read(buffer))!=-1){output.write(buffer,0,count);total+=count;}
                output.flush();
            }
            if(length>=0 && total!=length)throw new IOException("The transfer ended before every byte arrived");
        } finally {connection.disconnect();}
        return readBack(destination,address,expected);
    }
    public Saved readBack(Uri uri,String address,String expected)throws Exception {
        URL url=archiveUrl(address);byte[] raw;
        try(InputStream input=resolver.openInputStream(uri)) {
            if(input==null)throw new IOException("The saved file cannot be reopened");
            raw=ArchiveVerifier.readManifest(input,expected);
        }
        JSONObject manifest=new JSONObject(new String(raw,StandardCharsets.UTF_8));
        String id=manifest.getString("transfer_id");
        if(manifest.getInt("schema_version")!=1 || !url.getPath().equals("/api/transfers/"+id+"/archive"))throw new IOException("Transfer identity differs");
        if(manifest.getString("ack_token").length()<32 || manifest.getString("device_id").isEmpty())throw new IOException("Transfer confirmation is missing");
        JSONArray files=manifest.getJSONArray("files");Map<String,ArchiveVerifier.Entry> expectedFiles=new HashMap<>();
        if(files.length()>100000)throw new IOException("Transfer contains too many files");
        for(int i=0;i<files.length();i++) {
            JSONObject file=files.getJSONObject(i);String path=file.getString("path");
            if(expectedFiles.put(path,new ArchiveVerifier.Entry(file.getLong("bytes"),file.getString("sha256")))!=null)throw new IOException("Manifest repeats a file");
        }
        try(InputStream input=resolver.openInputStream(uri)) {
            if(input==null)throw new IOException("The saved file cannot be reopened");
            ArchiveVerifier.verify(input,expectedFiles,expected);
        }
        return new Saved(uri,address,expected,manifest);
    }
    public void acknowledge(Saved saved)throws Exception {post(saved,"ack");}
    public void release(Saved saved)throws Exception {post(saved,"release");}
    private void post(Saved saved,String action)throws Exception {
        URL archive=archiveUrl(saved.url);
        URL endpoint=new URL(archive.getProtocol(),archive.getHost(),archive.getPort(),"/api/transfers/"+saved.manifest.getString("transfer_id")+"/"+action);
        HttpURLConnection connection=open(endpoint);
        try {
            connection.setRequestMethod("POST");connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json");
            String origin=archive.getProtocol()+"://"+archive.getAuthority();connection.setRequestProperty("Origin",origin);
            byte[] body=new JSONObject().put("ack_token",saved.manifest.getString("ack_token"))
                .put("manifest_sha256",saved.manifestHash).put("device_id",saved.manifest.getString("device_id"))
                .put("verified",true).toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(body.length);
            try(OutputStream output=connection.getOutputStream()){output.write(body);}
            if(connection.getResponseCode()!=200)throw new IOException("The Pi did not confirm "+action+". Its files may have changed; save a new transfer.");
            String state;
            try(InputStream input=connection.getInputStream()){
                ByteArrayOutputStream result=new ByteArrayOutputStream();byte[] buffer=new byte[4096];int count;
                while((count=input.read(buffer))!=-1){if(result.size()+count>65536)throw new IOException("Invalid transfer confirmation");result.write(buffer,0,count);}
                state=new JSONObject(new String(result.toByteArray(),StandardCharsets.UTF_8)).getString("state");
            }
            if(!"released".equals(state) && !("ack".equals(action) && "verified".equals(state)))throw new IOException("The Pi did not confirm transfer state");
        } finally {connection.disconnect();}
    }
}
