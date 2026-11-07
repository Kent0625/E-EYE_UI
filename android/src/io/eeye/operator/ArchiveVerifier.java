package io.eeye.operator;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Verifies stored transfer bytes without filesystem or Android dependencies. */
public final class ArchiveVerifier {
    public static final String MANIFEST="transfer-manifest.json";
    private static final int MAX_MANIFEST=1024*1024;
    public interface Source {InputStream open()throws IOException;}
    public static final class Entry {
        public final long bytes;
        public final String sha256;
        public Entry(long bytes,String sha256)throws IOException {
            if(bytes<0 || !validHash(sha256))throw new IOException("Invalid file declaration");
            this.bytes=bytes;this.sha256=sha256;
        }
    }
    public static boolean validHash(String value) { return value!=null && value.matches("[0-9a-f]{64}"); }
    public static boolean safePath(String path) {
        if(path==null || path.isEmpty() || path.length()>512 || path.startsWith("/") || path.contains("\\") || path.contains(":") || path.indexOf('\0')>=0)return false;
        for(String segment:path.split("/",-1))if(segment.isEmpty() || segment.equals(".") || segment.equals(".."))return false;
        return true;
    }
    private static MessageDigest digest()throws IOException {
        try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException error){throw new IOException(error);}
    }
    private static String hex(byte[] value) { StringBuilder out=new StringBuilder();for(byte b:value)out.append(String.format("%02x",b&255));return out.toString(); }
    private static byte[] manifestBytes(ZipInputStream zip,String expected)throws IOException {
        if(!validHash(expected))throw new IOException("Missing manifest checksum");
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int count;
        while((count=zip.read(buffer))!=-1){if(out.size()+count>MAX_MANIFEST)throw new IOException("Manifest is too large");out.write(buffer,0,count);}
        byte[] bytes=out.toByteArray();
        if(!hex(digest().digest(bytes)).equals(expected))throw new IOException("Manifest checksum differs");
        return bytes;
    }
    public static byte[] readManifest(InputStream input,String expected)throws IOException {
        try(ZipInputStream zip=new ZipInputStream(input)) {
            ZipEntry entry=zip.getNextEntry();
            if(entry==null || !MANIFEST.equals(entry.getName()) || entry.isDirectory())throw new IOException("Manifest must be the first archive entry");
            return manifestBytes(zip,expected);
        }
    }
    public static void verify(Source source,Map<String,Entry> expected,String manifestHash,String archiveHash,long archiveBytes)throws IOException {
        if(!validHash(archiveHash) || archiveBytes<=0)throw new IOException("Missing archive checksum or byte count");
        MessageDigest raw=digest();long total=0;byte[] buffer=new byte[65536];int count;
        try(InputStream input=source.open()) {
            if(input==null)throw new IOException("The saved archive cannot be reopened");
            while((count=input.read(buffer))!=-1){total+=count;if(total>archiveBytes)throw new IOException("Archive byte count differs");raw.update(buffer,0,count);}
        }
        if(total!=archiveBytes || !hex(raw.digest()).equals(archiveHash))throw new IOException("Stored archive checksum differs");
        try(InputStream input=source.open()) {
            if(input==null)throw new IOException("The saved archive cannot be reopened");
            verifyEntries(input,expected,manifestHash);
        }
    }
    private static void verifyEntries(InputStream input,Map<String,Entry> expected,String manifestHash)throws IOException {
        if(expected.isEmpty() || expected.size()>100000)throw new IOException("Invalid manifest file count");
        for(String path:expected.keySet())if(!safePath(path) || MANIFEST.equals(path))throw new IOException("Invalid manifest path");
        Set<String> seen=new HashSet<>();boolean gotManifest=false;
        try(ZipInputStream zip=new ZipInputStream(input)) {
            ZipEntry entry;byte[] buffer=new byte[65536];
            while((entry=zip.getNextEntry())!=null){
                String path=entry.getName();
                if(!safePath(path) || entry.isDirectory() || !seen.add(path))throw new IOException("Duplicate or invalid archive path");
                if(MANIFEST.equals(path)) {if(seen.size()!=1)throw new IOException("Manifest must be first");manifestBytes(zip,manifestHash);gotManifest=true;continue;}
                Entry file=expected.get(path);if(file==null)throw new IOException("Unexpected archive entry");
                MessageDigest hash=digest();long total=0;int count;
                while((count=zip.read(buffer))!=-1){total+=count;if(total>file.bytes)throw new IOException("File size differs");hash.update(buffer,0,count);}
                if(total!=file.bytes || !hex(hash.digest()).equals(file.sha256))throw new IOException("Stored file checksum differs");
            }
        }
        if(!gotManifest || seen.size()!=expected.size()+1)throw new IOException("Archive is missing files");
    }
    private ArchiveVerifier() {}
}
