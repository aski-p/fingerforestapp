package com.openclaw.fruitauto;

import android.app.Activity;
import android.app.AlarmManager;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST_CODE = 20260529;
    private static final String APP_VERSION = "3.8.1";
    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private static final String APP_URL = "https://web-production-011c4.up.railway.app/?token=IV2d0ecXO9X50cJvmOHb-lI7wCSRiFji";
    private static final String FALLBACK_APP_URL = "https://web-production-011c4.up.railway.app/?token=IV2d0ecXO9X50cJvmOHb-lI7wCSRiFji";
    static final String BASE_URL = "https://web-production-011c4.up.railway.app";
    static final String FALLBACK_BASE_URL = "https://web-production-011c4.up.railway.app";
    static final String FRUIT_TOKEN = "IV2d0ecXO9X50cJvmOHb-lI7wCSRiFji";
    private static final long PRIMARY_LOAD_TIMEOUT_MS = 8000L;
    private boolean fallbackLoaded = false;
    private boolean mainFrameLoaded = false;
    private boolean exitDialogShowing = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestNotificationPermission();
        webView = new WebView(this);
        setContentView(webView);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        webView.addJavascriptInterface(new FruitBridge(this), "FruitAndroid");
        clearLegacySensitiveStorage();
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (MainActivity.this.filePathCallback != null) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                }
                MainActivity.this.filePathCallback = filePathCallback;
                Intent intent;
                try {
                    intent = fileChooserParams.createIntent();
                } catch (Exception _error) {
                    intent = new Intent(Intent.ACTION_GET_CONTENT);
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    intent.setType("image/*");
                }
                try {
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE);
                } catch (Exception _error) {
                    MainActivity.this.filePathCallback = null;
                    filePathCallback.onReceiveValue(null);
                    return false;
                }
                return true;
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return openExternalIfNeeded(request.getUrl().toString());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return openExternalIfNeeded(url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                mainFrameLoaded = true;
                if (!fallbackLoaded && url != null && url.startsWith(BASE_URL)) {
                    view.evaluateJavascript(
                        "(function(){var text=(document.body&&document.body.innerText||'').toLowerCase();return text.indexOf('502 bad gateway')>=0||text.indexOf('unable to reach the origin service')>=0||text.indexOf('cloudflared')>=0;})()",
                        value -> {
                            if ("true".equals(value)) loadFallbackIfNeeded();
                        }
                    );
                }
                view.evaluateJavascript(
                    "(function(){try{if(!window.FruitAndroid)return;['fruitToken','fruitTheme','fruitFont','fruitProfilePhoto','fruitProfilePhotoCache','fruitUiLoggedOut','fruitSecurityMigrationV85'].forEach(function(k){var v=localStorage.getItem(k);if(v!==null)window.FruitAndroid.saveLocal(k,v)})}catch(e){}})();",
                    null
                );
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request != null && request.isForMainFrame()) loadFallbackIfNeeded();
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                super.onReceivedHttpError(view, request, errorResponse);
                if (request == null || !request.isForMainFrame() || errorResponse == null) return;
                int statusCode = errorResponse.getStatusCode();
                if (statusCode == 530 || statusCode >= 500) loadFallbackIfNeeded();
            }
        });
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            openExternal(this, url);
        });
        webView.loadUrl(APP_URL);
        webView.postDelayed(() -> {
            if (!mainFrameLoaded) loadFallbackIfNeeded();
        }, PRIMARY_LOAD_TIMEOUT_MS);
        scheduleNotificationChecks(this);
    }

    private void clearLegacySensitiveStorage() {
        SharedPreferences prefs = getSharedPreferences("fruit-auto", MODE_PRIVATE);
        SharedPreferences uiPrefs = getSharedPreferences("fruit-auto-ui", MODE_PRIVATE);
        if ("1".equals(uiPrefs.getString("fruitSecurityMigrationV86", ""))) return;
        prefs.edit()
            .remove("sessionToken")
            .putBoolean("autoEnabled", false)
            .apply();
        uiPrefs.edit()
            .remove("fruitSessionToken")
            .remove("fruitCachedState")
            .remove("fruitRememberLogin")
            .remove("fruitRememberLoginId")
            .remove("fruitRememberLoginPw")
            .remove("fruitOwnerKey")
            .remove("fruitDeviceId")
            .remove("fruitSecurityMigrationV70")
            .remove("fruitSecurityMigrationV58")
            .remove("fruitSecurityMigrationV62")
            .remove("fruitSecurityMigrationV82")
            .remove("fruitSecurityMigrationV85")
            .remove("fruitActiveApiBaseV26")
            .remove("fruitUiLoggedOut")
            .putString("fruitSecurityMigrationV86", "1")
            .apply();
    }

    private boolean openExternalIfNeeded(String url) {
        if (url == null || url.isEmpty() || url.startsWith(BASE_URL) || url.startsWith(FALLBACK_BASE_URL)) return false;
        return openExternal(this, url);
    }

    private void loadFallbackIfNeeded() {
        if (fallbackLoaded || webView == null) return;
        fallbackLoaded = true;
        mainFrameLoaded = false;
        webView.post(() -> webView.loadUrl(FALLBACK_APP_URL));
    }

    private static boolean openExternal(Context context, String url) {
        if (url == null || url.isEmpty()) return false;
        if (url.contains("qr.kakaopay.com")) {
            Intent kakaoIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            kakaoIntent.setPackage("com.kakao.talk");
            kakaoIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                context.startActivity(kakaoIntent);
                return true;
            } catch (Exception _error) {
                // Fall back to any browser/app that can handle the KakaoPay URL.
            }
        }
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(intent);
        } catch (Exception _error) {
            return false;
        }
        return true;
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1001);
        }
    }

    static void scheduleNotificationChecks(Context context) {
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        Intent intent = new Intent(context, FruitNotificationReceiver.class);
        PendingIntent pendingIntent = PendingIntent.getBroadcast(
            context,
            20260528,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        SharedPreferences prefs = context.getSharedPreferences("fruit-auto", MODE_PRIVATE);
        boolean autoEnabled = prefs.getBoolean("autoEnabled", false);
        boolean pushEnabled = prefs.getBoolean("pushEnabled", true);
        String sessionToken = prefs.getString("sessionToken", "");
        if (!autoEnabled || !pushEnabled || sessionToken == null || sessionToken.isEmpty()) {
            alarmManager.cancel(pendingIntent);
            return;
        }
        int minutes = Math.max(5, Math.min(60, prefs.getInt("runIntervalMinutes", 5)));
        long nextRun = System.currentTimeMillis() + (minutes * 60_000L);
        if (Build.VERSION.SDK_INT >= 23) {
            alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, nextRun, pendingIntent);
        } else {
            alarmManager.set(AlarmManager.RTC_WAKEUP, nextRun, pendingIntent);
        }
    }

    static class FruitBridge {
        private final Context context;

        FruitBridge(Context context) {
            this.context = context.getApplicationContext();
        }

        @JavascriptInterface
        public void saveSession(String sessionToken) {
            boolean hasSession = sessionToken != null && !sessionToken.isEmpty();
            context.getSharedPreferences("fruit-auto", MODE_PRIVATE)
                .edit()
                .putString("sessionToken", sessionToken == null ? "" : sessionToken)
                .putBoolean("autoEnabled", hasSession && context.getSharedPreferences("fruit-auto", MODE_PRIVATE).getBoolean("autoEnabled", false))
                .apply();
            if (hasSession) {
                FruitNotificationReceiver.checkNow(context);
            } else {
                MainActivity.scheduleNotificationChecks(context);
            }
        }

        @JavascriptInterface
        public String getSession() {
            return context.getSharedPreferences("fruit-auto", MODE_PRIVATE)
                .getString("sessionToken", "");
        }

        @JavascriptInterface
        public void saveLocal(String key, String value) {
            if (key == null || key.isEmpty()) return;
            context.getSharedPreferences("fruit-auto-ui", MODE_PRIVATE)
                .edit()
                .putString(key, value == null ? "" : value)
                .apply();
        }

        @JavascriptInterface
        public String getLocal(String key) {
            if (key == null || key.isEmpty()) return "";
            if ("fruitRememberLoginPw".equals(key) || "fruitSessionToken".equals(key)) return "";
            return context.getSharedPreferences("fruit-auto-ui", MODE_PRIVATE)
                .getString(key, "");
        }

        @JavascriptInterface
        public void removeLocal(String key) {
            if (key == null || key.isEmpty()) return;
            context.getSharedPreferences("fruit-auto-ui", MODE_PRIVATE)
                .edit()
                .remove(key)
                .apply();
        }

        @JavascriptInterface
        public void saveSettings(boolean autoEnabled, boolean pushEnabled, int runIntervalMinutes) {
            int minutes = Math.max(5, Math.min(60, runIntervalMinutes));
            context.getSharedPreferences("fruit-auto", MODE_PRIVATE)
                .edit()
                .putBoolean("autoEnabled", autoEnabled)
                .putBoolean("pushEnabled", pushEnabled)
                .putInt("runIntervalMinutes", minutes)
                .apply();
            MainActivity.scheduleNotificationChecks(context);
        }

        @JavascriptInterface
        public void showNotification(String title, String body) {
            FruitNotificationReceiver.showNotification(
                context,
                title == null ? "fingerfruit" : title,
                body == null ? "열매 수신 내역이 있습니다." : body
            );
        }

        @JavascriptInterface
        public void openSupport(String url) {
            MainActivity.openExternal(context, url);
        }

        @JavascriptInterface
        public String getAppVersion() {
            return MainActivity.APP_VERSION;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER_REQUEST_CODE || filePathCallback == null) return;
        Uri[] results = null;
        if (resultCode == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                int count = data.getClipData().getItemCount();
                results = new Uri[count];
                for (int i = 0; i < count; i++) {
                    results[i] = data.getClipData().getItemAt(i).getUri();
                }
            } else if (data.getData() != null) {
                results = new Uri[]{data.getData()};
            }
        }
        filePathCallback.onReceiveValue(results);
        filePathCallback = null;
    }

    @Override
    public void onBackPressed() {
        if (webView == null) {
            confirmExit();
            return;
        }
        webView.evaluateJavascript(
            "(function(){try{return !!(window.FruitAppBack&&window.FruitAppBack.handleBackPress&&window.FruitAppBack.handleBackPress());}catch(e){return false;}})();",
            value -> {
                if ("true".equals(value)) return;
                if (webView != null && webView.canGoBack()) {
                    webView.goBack();
                    return;
                }
                confirmExit();
            }
        );
    }

    private void confirmExit() {
        if (exitDialogShowing || isFinishing()) return;
        exitDialogShowing = true;
        new AlertDialog.Builder(this)
            .setMessage("앱을 종료하겠습니까?")
            .setPositiveButton("확인", (_dialog, _which) -> {
                exitDialogShowing = false;
                finish();
            })
            .setNegativeButton("아니오", (_dialog, _which) -> exitDialogShowing = false)
            .setOnCancelListener(_dialog -> exitDialogShowing = false)
            .show();
    }
}
