package com.bizcrax36.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.view.KeyEvent
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * BizCrax36 — 360° Command Center (APK backup).
 *
 * Single source of truth: renders web/index.html from app assets (copied at
 * build time) and proxies every /api/ request to the configured BizCrax36
 * backend (python -m backend.web_api). The UI and engine output are therefore
 * byte-identical to the HTML deployment.
 *
 * Set the backend host with a long-press (persisted in SharedPreferences).
 * Emulator default: http://10.0.2.2:8765 (host loopback). On a phone, use the
 * machine's LAN IP, e.g. http://192.168.1.20:8765 — run web_api with
 * --host 0.0.0.0 and allow TCP 8765.
 */
class MainActivity : Activity() {

    private lateinit var webView: WebView

    private fun prefs() =
        getSharedPreferences("bizcrax36", Context.MODE_PRIVATE)

    private fun backend(): String {
        var url = prefs().getString("backend", DEFAULT_BACKEND) ?: DEFAULT_BACKEND
        url = url.trim().removeSuffix("/")
        if (url.isBlank()) url = DEFAULT_BACKEND
        if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://$url"
        return url
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
        }
        webView.settings.userAgentString =
            (webView.settings.userAgentString ?: "") + " BizCrax36/2.0 (apk)"
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                return when {
                    url.path?.startsWith("/api/") == true -> {
                        // Same-origin look-alike: redirect to the real backend so
                        // the browser (JS fetch) talks to the Python engine.
                        view.loadUrl(backend() + url.encodedPath +
                            (if (url.query != null) "?${url.query}" else ""))
                        true
                    }
                    else -> false
                }
            }
        }
        setContentView(webView)
        webView.setOnLongClickListener { showServerDialog(); true }
        loadAsset()
    }

    private fun loadAsset() {
        val target = "file:///android_asset/web/index.html"
        if (webView.url == target) webView.reload() else webView.loadUrl(target)
    }

    private fun showServerDialog() {
        val input = android.widget.EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_URI
            setText(backend())
        }
        AlertDialog.Builder(this)
            .setTitle("BizCrax36 backend")
            .setMessage("Host the Python web API (python -m backend.web_api --host 0.0.0.0).\n" +
                "Example: http://192.168.1.20:8765\nEmulator: http://10.0.2.2:8765\n\nLong-press to change.")
            .setView(input)
            .setPositiveButton("Save") { _, _ ->
                prefs().edit().putString("backend", input.text.toString().trim()).apply()
                loadAsset()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    companion object {
        private const val DEFAULT_BACKEND = "http://10.0.2.2:8765"
    }
}
