package com.v2dstudio.app;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.TextView;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            WebView web = new WebView(this);
            WebSettings s = web.getSettings();
            s.setJavaScriptEnabled(true);
            s.setDomStorageEnabled(true);
            s.setLoadWithOverviewMode(true);
            s.setUseWideViewPort(true);
            web.setWebViewClient(new WebViewClient());
            web.loadUrl("https://v2d-studio.onrender.com");
            setContentView(web);
        } catch (Throwable t) {
            // Show any startup error on screen instead of silently crashing.
            TextView tv = new TextView(this);
            tv.setTextColor(Color.RED);
            tv.setTextSize(16);
            tv.setGravity(Gravity.CENTER);
            tv.setPadding(24, 24, 24, 24);
            tv.setText("Startup error:\n" + (t.getMessage() == null ? t.toString() : t.getMessage()));
            setContentView(tv);
        }
    }
}
