package dev.solorion.nebulatv

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import com.google.zxing.BarcodeFormat
import com.google.zxing.MultiFormatWriter
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * NebulaTV — a leanback WebView shell around the Nebula web UI.
 *
 * The TV app owns no Nebula logic: it loads the same web app Scotty uses in
 * a browser, keeps the DSECT login cookie alive across restarts, and makes
 * the remote control behave (D-pad focus navigation inside the page,
 * Back = web back, Menu = environment / sign-in options).
 *
 * QR sign-in (v0.2): typing a password with a TV remote is miserable, so the
 * app can run Nebula's device-login flow instead — it asks the server for a
 * pairing, renders the approval URL as a QR code (ZXing), polls until the
 * phone approves, then stores the returned session JWT as the WebView's
 * cc_token cookie and reloads Nebula signed in. The phone's credentials
 * never touch the TV.
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
        private const val DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
    }

    private lateinit var rootLayout: FrameLayout
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var qrShortcutButton: Button
    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    // --- QR sign-in state (one flow at a time) ---
    private val mainHandler = Handler(Looper.getMainLooper())
    private var qrExecutor: ExecutorService? = null
    private val qrActive = AtomicBoolean(false)
    private var qrOverlay: View? = null
    private var qrDeviceCode: String? = null
    private var qrBaseUrl: String = URL_PRODUCTION

    private fun currentBaseUrl(): String {
        val env = getSharedPreferences(PREFS, MODE_PRIVATE).getString(PREF_ENV, ENV_PROD)
        return if (env == ENV_EXP) URL_EXPERIMENTAL else URL_PRODUCTION
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        rootLayout = FrameLayout(this)
        webView = WebView(this)
        progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 6, Gravity.TOP
            )
        }
        rootLayout.addView(webView, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        rootLayout.addView(progressBar)

        // Shown only while Nebula's own login form is on screen (detected in
        // onPageFinished): a remote-friendly shortcut into QR sign-in.
        qrShortcutButton = Button(this).apply {
            text = "Sign in with QR code"
            visibility = View.GONE
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            ).apply { bottomMargin = 36 }
            setOnClickListener { showQrSignIn() }
        }
        rootLayout.addView(qrShortcutButton)
        setContentView(rootLayout)

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
            // Identify the TV app to the web UI so it enables TV mode
            // (10-foot layout + D-pad spatial navigation, TRK-0524).
            userAgentString = (userAgentString ?: "") + " NebulaTV/0.3"
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

            override fun onPageFinished(view: WebView, url: String?) {
                super.onPageFinished(view, url)
                // Offer the QR shortcut exactly when Nebula is showing its
                // login form (the SPA marks it with .neb-login).
                view.evaluateJavascript(
                    "(function(){return !!document.querySelector('.neb-login');})()"
                ) { result ->
                    val loginVisible = result == "true"
                    runOnUiThread {
                        qrShortcutButton.visibility =
                            if (loginVisible && qrOverlay == null) View.VISIBLE else View.GONE
                    }
                }
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
            <p style="color:#999">Press Menu on the remote for sign-in and
            environment options.</p></div></body></html>
        """.trimIndent()
        webView.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    // ------------------------------------------------------------ QR sign-in

    private fun postJson(url: String, body: JSONObject): Pair<Int, JSONObject?> {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 10_000
            conn.readTimeout = 10_000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.let {
                BufferedReader(InputStreamReader(it, Charsets.UTF_8)).readText()
            } ?: ""
            val json = try { JSONObject(text) } catch (e: Exception) { null }
            return code to json
        } finally {
            conn.disconnect()
        }
    }

    private fun qrBitmap(contents: String, size: Int = 720): Bitmap {
        val matrix = MultiFormatWriter().encode(contents, BarcodeFormat.QR_CODE, size, size)
        val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.RGB_565)
        for (x in 0 until size) {
            for (y in 0 until size) {
                bmp.setPixel(x, y, if (matrix[x, y]) Color.BLACK else Color.WHITE)
            }
        }
        return bmp
    }

    private fun stopQrFlow(notifyServer: Boolean) {
        qrActive.set(false)
        qrExecutor?.shutdownNow()
        qrExecutor = null
        val code = qrDeviceCode
        val base = qrBaseUrl
        qrDeviceCode = null
        if (notifyServer && code != null) {
            Executors.newSingleThreadExecutor().execute {
                try {
                    postJson("$base/api/auth/device/cancel", JSONObject().put("device_code", code))
                } catch (e: Exception) {
                    // Best effort: the pairing expires on its own in minutes.
                }
            }
        }
    }

    private fun closeQrOverlay() {
        qrOverlay?.let { rootLayout.removeView(it) }
        qrOverlay = null
        webView.visibility = View.VISIBLE
        webView.requestFocus()
    }

    private fun showQrSignIn() {
        stopQrFlow(notifyServer = false)
        qrBaseUrl = currentBaseUrl()
        val base = qrBaseUrl

        val overlay = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#14142B"))
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
            )
            setPadding(48, 32, 48, 32)
        }
        val title = TextView(this).apply {
            text = "Sign in with your phone"
            textSize = 30f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        val instructions = TextView(this).apply {
            text = "Scan the QR code with your phone and approve “Nebula TV”. " +
                "This screen signs itself in — no typing on the TV."
            textSize = 18f
            setTextColor(Color.parseColor("#C9C9D8"))
            gravity = Gravity.CENTER
        }
        val qrImage = ImageView(this).apply {
            layoutParams = LinearLayout.LayoutParams(380, 380).apply { topMargin = 24 }
        }
        val codeText = TextView(this).apply {
            textSize = 26f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        val urlText = TextView(this).apply {
            textSize = 15f
            setTextColor(Color.parseColor("#9A9AB0"))
            gravity = Gravity.CENTER
        }
        val status = TextView(this).apply {
            text = "Contacting Nebula…"
            textSize = 17f
            setTextColor(Color.parseColor("#C9C9D8"))
            gravity = Gravity.CENTER
        }
        val cancelButton = Button(this).apply {
            text = "Cancel"
            setOnClickListener {
                stopQrFlow(notifyServer = true)
                closeQrOverlay()
            }
        }
        val retryButton = Button(this).apply {
            text = "Try again"
            visibility = View.GONE
            setOnClickListener { showQrSignIn() }
        }
        overlay.addView(title)
        overlay.addView(instructions)
        overlay.addView(qrImage)
        overlay.addView(codeText)
        overlay.addView(urlText)
        overlay.addView(status)
        overlay.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            addView(cancelButton)
            addView(retryButton)
        })
        qrOverlay = overlay
        qrShortcutButton.visibility = View.GONE
        rootLayout.addView(overlay)
        webView.visibility = View.INVISIBLE
        cancelButton.requestFocus()

        fun fail(message: String) {
            mainHandler.post {
                status.text = message
                retryButton.visibility = View.VISIBLE
                retryButton.requestFocus()
            }
        }

        qrActive.set(true)
        val executor = Executors.newSingleThreadExecutor()
        qrExecutor = executor
        executor.execute {
            val created: JSONObject
            try {
                val (code, json) = postJson(
                    "$base/api/auth/device/start",
                    JSONObject().put("device_name", "Nebula TV")
                )
                if (code != 200 || json == null) {
                    fail(
                        if (code == 404)
                            "QR sign-in isn't available on this Nebula server yet."
                        else "Couldn't start QR sign-in (HTTP $code)."
                    )
                    return@execute
                }
                created = json
            } catch (e: Exception) {
                fail("Couldn't reach Nebula to start QR sign-in.")
                return@execute
            }

            val deviceCode = created.optString("device_code")
            val qrUrl = created.optString("verification_uri_complete")
            val userCode = created.optString("user_code")
            val verifyUri = created.optString("verification_uri")
            val expiresIn = created.optLong("expires_in", 600)
            var intervalSec = created.optLong("interval", 5).coerceAtLeast(3)
            qrDeviceCode = deviceCode
            val deadline = System.currentTimeMillis() + expiresIn * 1000

            mainHandler.post {
                try {
                    qrImage.setImageBitmap(qrBitmap(qrUrl))
                } catch (e: Exception) {
                    status.text = "Couldn't draw the QR code."
                }
                codeText.text = userCode
                urlText.text = "No camera? Open $verifyUri and enter the code."
                status.text = "Waiting for approval on your phone…"
            }

            // Poll until approval, denial, expiry, or cancel.
            while (qrActive.get() && System.currentTimeMillis() < deadline) {
                try {
                    Thread.sleep(intervalSec * 1000)
                } catch (e: InterruptedException) {
                    return@execute
                }
                if (!qrActive.get()) return@execute
                try {
                    val (code, json) = postJson(
                        "$base/api/auth/device/token",
                        JSONObject()
                            .put("grant_type", DEVICE_GRANT)
                            .put("device_code", deviceCode)
                    )
                    if (code == 200 && json != null) {
                        val token = json.optString("access_token")
                        if (token.isNotEmpty()) {
                            qrActive.set(false)
                            mainHandler.post { onQrApproved(base, token) }
                            return@execute
                        }
                    }
                    when (json?.optString("error")) {
                        "authorization_pending" -> Unit // keep waiting
                        "slow_down" -> intervalSec =
                            (json.optLong("interval", intervalSec + 5)).coerceAtMost(30)
                        "access_denied" -> {
                            fail("Sign-in was denied on the phone.")
                            return@execute
                        }
                        "expired_token" -> {
                            fail("That code expired. Try again for a fresh one.")
                            return@execute
                        }
                        else -> Unit // transient server hiccup: keep waiting
                    }
                } catch (e: Exception) {
                    // Transient network failure: keep polling until deadline.
                }
            }
            if (qrActive.get()) {
                fail("That code expired. Try again for a fresh one.")
            }
        }
    }

    private fun onQrApproved(base: String, token: String) {
        stopQrFlow(notifyServer = false)
        val cookieManager = CookieManager.getInstance()
        // Same cookie the web login sets; the JWT itself expires in 24h
        // server-side regardless of the cookie's client-side lifetime.
        val cookie = "cc_token=$token; Path=/; Secure; HttpOnly; SameSite=Lax"
        cookieManager.setCookie(base, cookie) {
            cookieManager.flush()
            closeQrOverlay()
            webView.loadUrl(base)
        }
    }

    // ------------------------------------------------------------------ misc

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
                if (qrOverlay != null) {
                    stopQrFlow(notifyServer = true)
                    closeQrOverlay()
                } else if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    confirmExit()
                }
                return true
            }
            KeyEvent.KEYCODE_MENU -> {
                showOptionsDialog()
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

    private fun showOptionsDialog() {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        val isExp = prefs.getString(PREF_ENV, ENV_PROD) == ENV_EXP
        val labels = arrayOf(
            (if (!isExp) "✓ " else "") + "Production — nebula.solorion.dev",
            (if (isExp) "✓ " else "") + "Experimental — nebula-exp.solorion.dev",
            "Sign in with QR code"
        )
        AlertDialog.Builder(this)
            .setTitle("Nebula")
            .setItems(labels) { dialog, which ->
                dialog.dismiss()
                when (which) {
                    0, 1 -> {
                        val env = if (which == 1) ENV_EXP else ENV_PROD
                        prefs.edit().putString(PREF_ENV, env).apply()
                        webView.loadUrl(currentBaseUrl())
                    }
                    2 -> showQrSignIn()
                }
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
        stopQrFlow(notifyServer = false)
        filePathCallback?.onReceiveValue(null)
        filePathCallback = null
        webView.destroy()
        super.onDestroy()
    }
}
