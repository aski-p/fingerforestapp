package com.openclaw.fruitauto;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.widget.Toast;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

// In-app update (3.20.0+): downloads a FingerForest APK from our own server and hands it to the system
// installer through a PackageInstaller session. The person still confirms the install on the system sheet.
final class ApkUpdater {
    private static volatile boolean running = false;

    private ApkUpdater() {}

    static boolean isOwnApk(String url) {
        if (url == null) return false;
        boolean ours = url.startsWith(MainActivity.BASE_URL + "/") || url.startsWith(MainActivity.FALLBACK_BASE_URL + "/");
        String path = Uri.parse(url).getPath();
        return ours && path != null && path.endsWith(".apk");
    }

    static void start(Activity activity, String url) {
        if (!isOwnApk(url)) return;
        if (Build.VERSION.SDK_INT >= 26 && !activity.getPackageManager().canRequestPackageInstalls()) {
            toast(activity, "업데이트하려면 'FingerForest 앱 설치 허용'을 켠 뒤 다시 눌러 주세요");
            try {
                activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + activity.getPackageName())));
            } catch (Exception _error) {
                // Settings screen missing on this device; the installer sheet will ask instead.
            }
            return;
        }
        if (running) return;
        running = true;
        toast(activity, "새 버전을 내려받는 중이에요");
        final Context app = activity.getApplicationContext();
        new Thread(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(url).openConnection();
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(60000);
                if (connection.getResponseCode() != 200) throw new IllegalStateException("HTTP " + connection.getResponseCode());
                long length = connection.getContentLengthLong();
                PackageInstaller installer = app.getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                if (length > 0) params.setSize(length);
                int sessionId = installer.createSession(params);
                try (PackageInstaller.Session session = installer.openSession(sessionId)) {
                    try (InputStream in = connection.getInputStream(); OutputStream out = session.openWrite("fingerforest.apk", 0, length > 0 ? length : -1)) {
                        byte[] buffer = new byte[64 * 1024];
                        int read;
                        while ((read = in.read(buffer)) != -1) out.write(buffer, 0, read);
                        session.fsync(out);
                    }
                    int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                    PendingIntent result = PendingIntent.getBroadcast(app, sessionId, new Intent(app, InstallResultReceiver.class), flags);
                    session.commit(result.getIntentSender());
                }
            } catch (Exception error) {
                activity.runOnUiThread(() -> toast(activity, "업데이트를 내려받지 못했어요. 잠시 후 다시 시도해 주세요"));
            } finally {
                if (connection != null) connection.disconnect();
                running = false;
            }
        }).start();
    }

    static void toast(Context context, String text) {
        Toast.makeText(context, text, Toast.LENGTH_LONG).show();
    }
}
