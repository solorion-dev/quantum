package dev.solorion.nebulatv

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ProgressBar

/**
 * NebulaTV v0.1 — a leanback WebView shell around the Nebula web UI.
 *
 * The TV app owns no Nebula logic: it loads the same web app Scotty uses in
 * a browser, keeps the DSECT login cookie alive across restarts, and makes
 * the remote control behave (D-pad focus navigation inside the page,
 * Back = web back, Menu = switch production/experimental).
 */
class MainActivity : Activity() {

    companion object {
        const val URL_PRODUCTION = "https://nebula.solorion.dev"
        const val URL_EXPERIMENTAL = "https://nebula-exp.solorion.dev"
        private const val PREFS = "nebulatv"
        private const val PREF_ENV = "env"
        private const val ENV_PROD = "prod"
        private const val ENV_EXP = "exp"
        private const val FILE_CHOOSER_REQUEST = 1001
    }

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    private fun currentBaseUrl(): String {
        val env = getSharedPreferences(PREFS, MODE_PRIVATE).getString(PREF_ENV, ENV_PROD)
        return if (env == ENV_EXP) URL_EXPERIMENTAL else URL_PRODUCTION
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this)
        webView = WebView(this)
        progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 6, Gravity.TOP
            )
        }
        root.addView(webView, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        root.addView(progressBar)
        setContentView(root)

        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(webView, true)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowContentAccess = true
            // Uploads go through the system file picker (onShowFileChooser);
            // the WebView itself never needs raw file-system access.
            allowFileAccess = false
            setSupportZoom(false)
            // TV pages should render at desktop-like width.
            layoutAlgorithm = WebSettings.LayoutAlgorithm.TEXT_AUTOSIZING
        }
        webView.isFocusable = true
        webView.isFocusableInTouchMode = true

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView, request: WebResourceRequest
            ): Boolean {
                // Keep all navigation inside the TV WebView.
                return false
            }

            override fun onReceivedError(
                view: WebView, request: WebResourceRequest, error: WebResourceError
            ) {
                if (request.isForMainFrame) {
                    showErrorPage(error.description?.toString() ?: "Network error")
                }
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility =
                    if (newProgress >= 100) ProgressBar.GONE else ProgressBar.VISIBLE
            }

            override fun onShowFileChooser(
                view: WebView,
                callback: ValueCallback<Array<Uri>>,
                params: FileChooserParams
            ): Boolean {
                filePathCallback?.onReceiveValue(null)
                filePathCallback = callback
                return try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER_REQUEST)
                    true
                } catch (e: Exception) {
                    filePathCallback = null
                    false
                }
            }
        }

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState)
        } else {
            webView.loadUrl(currentBaseUrl())
        }
        webView.requestFocus()
    }

    private fun showErrorPage(message: String) {
        val url = currentBaseUrl()
        val html = """
            <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
            <style>body{background:#14142b;color:#eee;font-family:sans-serif;
            display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
            div{text-align:center}button{background:#5050c0;color:#fff;border:0;
            padding:14px 34px;font-size:20px;border-radius:8px}</style></head>
            <body><div><h1>Can't reach Nebula</h1><p>$message</p>
            <p><button onclick="location.href='$url'">Retry</button></p>
            <p style="color:#999">Press Menu on the remote to switch
            production / experimental.</p></div></body></html>
        """.trimIndent()
        webView.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == FILE_CHOOSER_REQUEST) {
            val results = WebChromeClient.FileChooserParams.parseResult(resultCode, data)
            filePathCallback?.onReceiveValue(results)
            filePathCallback = null
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        when (keyCode) {
            KeyEvent.KEYCODE_BACK -> {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    confirmExit()
                }
                return true
            }
            KeyEvent.KEYCODE_MENU -> {
                showEnvironmentDialog()
                return true
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    private fun confirmExit() {
        AlertDialog.Builder(this)
            .setTitle("Exit Nebula?")
            .setPositiveButton("Exit") { _, _ -> finish() }
            .setNegativeButton("Stay", null)
            .show()
    }

    private fun showEnvironmentDialog() {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        val current = if (prefs.getString(PREF_ENV, ENV_PROD) == ENV_EXP) 1 else 0
        val labels = arrayOf("Production — nebula.solorion.dev", "Experimental — nebula-exp.solorion.dev")
        AlertDialog.Builder(this)
            .setTitle("Nebula environment")
            .setSingleChoiceItems(labels, current) { dialog, which ->
                val env = if (which == 1) ENV_EXP else ENV_PROD
                prefs.edit().putString(PREF_ENV, env).apply()
                dialog.dismiss()
                webView.loadUrl(currentBaseUrl())
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onPause() {
        // Persist cookies (the DSECT session) so login survives restarts.
        CookieManager.getInstance().flush()
        webView.onPause()
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onDestroy() {
        filePathCallback?.onReceiveValue(null)
        filePathCallback = null
        webView.destroy()
        super.onDestroy()
    }
}
