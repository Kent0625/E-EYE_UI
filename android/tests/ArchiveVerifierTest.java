package io.eeye.operator;

import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

public final class ArchiveVerifierTest {
    static byte[] manifest="{\"schema_version\":1}".getBytes();
    static String hash(byte[] b)throws Exception { StringBuilder s=new StringBuilder(); for(byte x:MessageDigest.getInstance("SHA-256").digest(b))s.append(String.format("%02x",x)); return s.toString(); }
    static byte[] zip(String name,byte[] bytes)throws Exception {
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        try(ZipOutputStream z=new ZipOutputStream(out)) { z.putNextEntry(new ZipEntry("transfer-manifest.json")); z.write(manifest); z.closeEntry(); z.putNextEntry(new ZipEntry(name));z.write(bytes);z.closeEntry(); }
        return out.toByteArray();
    }
    static byte[] duplicate(byte[] bytes)throws Exception {
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        try(ZipOutputStream z=new ZipOutputStream(out)) {
            z.putNextEntry(new ZipEntry("transfer-manifest.json"));z.write(manifest);z.closeEntry();
            for(String name:new String[]{"captures/frame.jpg","captures/other.jpg"}){z.putNextEntry(new ZipEntry(name));z.write(bytes);z.closeEntry();}
        }
        byte[] result=out.toByteArray(),from="other.jpg".getBytes(),to="frame.jpg".getBytes();
        for(int i=0;i<=result.length-from.length;i++){boolean same=true;for(int j=0;j<from.length;j++)same&=result[i+j]==from[j];if(same)System.arraycopy(to,0,result,i,to.length);}
        return result;
    }
    static void rejected(byte[] zip,Map<String,ArchiveVerifier.Entry> expected,String digest)throws Exception {
        try { ArchiveVerifier.verify(new ByteArrayInputStream(zip),expected,digest); throw new AssertionError("Accepted invalid archive"); } catch(IOException good) {}
    }
    public static void main(String[] args)throws Exception {
        byte[] frame={1,2,3,4};
        Map<String,ArchiveVerifier.Entry> expected=new HashMap<>(); expected.put("captures/frame.jpg",new ArchiveVerifier.Entry(frame.length,hash(frame)));
        byte[] valid=zip("captures/frame.jpg",frame);
        ArchiveVerifier.verify(new ByteArrayInputStream(valid),expected,hash(manifest));
        if(!Arrays.equals(manifest,ArchiveVerifier.readManifest(new ByteArrayInputStream(valid),hash(manifest))))throw new AssertionError();
        rejected(zip("captures/frame.jpg",new byte[]{9,2,3,4}),expected,hash(manifest));
        rejected(zip("../frame.jpg",frame),expected,hash(manifest));
        rejected(zip("unexpected.jpg",frame),expected,hash(manifest));
        rejected(valid,expected,hash(frame));
        rejected(duplicate(frame),expected,hash(manifest));
        Map<String,ArchiveVerifier.Entry> missing=new HashMap<>(expected);missing.put("receipt.png",new ArchiveVerifier.Entry(1,hash(new byte[]{1})));rejected(valid,missing,hash(manifest));
        expected.put("captures/frame.jpg",new ArchiveVerifier.Entry(3,hash(frame)));rejected(valid,expected,hash(manifest));
        rejected(Arrays.copyOf(valid,valid.length/2),expected,hash(manifest));
        System.out.println("PASS: archive readback, hash, path, unexpected/missing entry, byte count and truncated data checks");
    }
}
