package com.openclaw.fruitauto;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class FruitNotificationReceiver extends BroadcastReceiver {
    private static final String CHANNEL_ID = "fruit-auto-transfer";

    @Override
    public void onReceive(Context context, Intent intent) {
        checkNow(context);
    }

    static void checkNow(Context context) {
        new Thread(() -> {
            try {
                SharedPreferences prefs = context.getSharedPreferences("fruit-auto", Context.MODE_PRIVATE);
                String sessionToken = prefs.getString("sessionToken", "");
                if (sessionToken == null || sessionToken.isEmpty()) return;

                JSONObject state = fetchJson("/api/status", sessionToken).getJSONObject("state");
                boolean autoEnabled = state.optBoolean("enabled", false);
                boolean pushEnabled = state.optBoolean("pushEnabled", true);
                int minutes = Math.max(5, Math.min(60, state.optInt("runIntervalMinutes", 5)));
                prefs.edit()
                    .putBoolean("autoEnabled", autoEnabled)
                    .putBoolean("pushEnabled", pushEnabled)
                    .putInt("runIntervalMinutes", minutes)
                    .apply();
                if (!autoEnabled || !pushEnabled) return;

                JSONObject root = fetchJson("/api/notifications", sessionToken);
                JSONArray items = root.getJSONObject("result").optJSONArray("items");
                if (items == null || items.length() == 0) return;

                JSONObject latest = items.getJSONObject(0);
                String id = latest.optString("id", "");
                String lastShownId = prefs.getString("lastShownNotificationId", "");
                if (id.isEmpty() || id.equals(lastShownId)) return;

                prefs.edit().putString("lastShownNotificationId", id).apply();
                showNotification(context, latest.optString("title", "FingerSnap"), latest.optString("body", "열매 전송 내역이 있습니다."));
            } catch (Exception ignored) {
            } finally {
                MainActivity.scheduleNotificationChecks(context);
            }
        }).start();
    }

    private static JSONObject fetchJson(String path, String sessionToken) throws Exception {
        Exception lastError = null;
        String[] bases = new String[]{MainActivity.BASE_URL, MainActivity.FALLBACK_BASE_URL};
        for (String base : bases) {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(base + path).openConnection();
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(15000);
                connection.setRequestProperty("X-Fruit-Token", MainActivity.FRUIT_TOKEN);
                connection.setRequestProperty("X-Fruit-Session", sessionToken);
                int responseCode = connection.getResponseCode();
                if (responseCode == 530 || responseCode >= 500) throw new IllegalStateException("HTTP " + responseCode);
                if (responseCode != 200) throw new IllegalStateException("HTTP " + responseCode);

                BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()));
                StringBuilder body = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) body.append(line);
                return new JSONObject(body.toString());
            } catch (Exception error) {
                lastError = error;
            } finally {
                if (connection != null) connection.disconnect();
            }
        }
        throw lastError == null ? new IllegalStateException("request failed") : lastError;
    }

    static void showNotification(Context context, String title, String body) {
        NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "열매 전송 알림", NotificationManager.IMPORTANCE_DEFAULT);
            manager.createNotificationChannel(channel);
        }

        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(context, CHANNEL_ID)
            : new Notification.Builder(context);
        builder
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body.replace("\n", " "))
            .setStyle(new Notification.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setShowWhen(true);
        manager.notify(20260528, builder.build());
    }
}
