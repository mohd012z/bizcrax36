# Keep the WebView bridge interface method (retained via @JavascriptInterface, but be explicit).
-keepclassmembers class com.bizcrax36.app.MainActivity$WebBridge {
    @android.webkit.JavascriptInterface <methods>;
}
