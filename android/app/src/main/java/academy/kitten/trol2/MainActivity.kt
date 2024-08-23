package academy.kitten.trol2


import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.util.Log
import android.webkit.ConsoleMessage
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import androidx.webkit.WebSettingsCompat
import androidx.webkit.WebViewFeature

class MainActivity : AppCompatActivity() {

    private val PREFS_NAME = "WebViewPrefs"
    private val URL_KEY = "url"
    private val DEFAULT_URL = "http://prime.scribblej.com:8000/test.html"

    private lateinit var webView: WebView
    private lateinit var swipeRefreshLayout: SwipeRefreshLayout
    private var cameraName = "Den"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Hide the action bar
        supportActionBar?.hide()
        // and just use a button
        val openSettingsButton: Button = findViewById(R.id.openSettingsButton)
        openSettingsButton.setOnClickListener {
            val intent = Intent(this, SettingsActivity::class.java)
            startActivity(intent)
        }


        swipeRefreshLayout = findViewById(R.id.swipeRefreshLayout)
        webView = findViewById(R.id.webView)

        val preferences = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val url = preferences.getString(URL_KEY, DEFAULT_URL)

        //webView.settings.javaScriptEnabled = true
        //webView.settings.cacheMode = WebSettings.LOAD_NO_CACHE
        //webView.settings.domStorageEnabled = true
        webView.settings.apply {
            javaScriptEnabled = true
            cacheMode = WebSettings.LOAD_NO_CACHE
            domStorageEnabled = true
            useWideViewPort = true  // Enable support for the viewport meta tag
            loadWithOverviewMode = true  // Zoom out to fit content
            builtInZoomControls = true  // Enable pinch-to-zoom
            displayZoomControls = false  // Disable the default zoom controls
            setSupportZoom(true)  // Support zooming
        }

        webView.clearCache(true)
        webView.clearHistory()

        webView.addJavascriptInterface(WebAppInterface(), "AndroidInterface")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, url: String): Boolean {
                return if (url.startsWith("myapp://")) {
                    val intent = Intent().apply {
                        action = Intent.ACTION_VIEW
                        component = ComponentName("com.alexvas.dvr.pro", "com.alexvas.dvr.activity.LiveViewActivity")
                        putExtra("com.alexvas.dvr.intent.extra.shortcut.NAME", cameraName)
                    }
                    startActivity(intent)
                    true
                } else {
                    false
                }
            }
        }

        // Capture JavaScript console messages
        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                Log.d("WebView", "${consoleMessage?.message()} -- From line ${consoleMessage?.lineNumber()} of ${consoleMessage?.sourceId()}")
                return true
            }
        }

        // url?.let { webView.loadUrl(it) }
        // We're going to try bundling the html/js instead.
        // Load the HTML file from the assets directory
        webView.loadUrl("file:///android_asset/trol2.html")


        swipeRefreshLayout.setOnRefreshListener {
            webView.reload()
            swipeRefreshLayout.isRefreshing = false
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_settings -> {
                val intent = Intent(this, SettingsActivity::class.java)
                startActivity(intent)
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    inner class WebAppInterface {
        @JavascriptInterface
        fun setCameraName(name: String) {
            cameraName = name
        }
    }
}
