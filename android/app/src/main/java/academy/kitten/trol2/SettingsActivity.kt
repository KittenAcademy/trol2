package academy.kitten.trol2

import android.content.Context
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {

    private val PREFS_NAME = "WebViewPrefs"
    private val URL_KEY = "url"

    private lateinit var urlEditText: EditText
    private lateinit var saveButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        urlEditText = findViewById(R.id.urlEditText)
        saveButton = findViewById(R.id.saveButton)

        val preferences = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val url = preferences.getString(URL_KEY, "http://prime.scribblej.com:8000/test.html")
        urlEditText.setText(url)

        saveButton.setOnClickListener {
            val newUrl = urlEditText.text.toString()
            preferences.edit().putString(URL_KEY, newUrl).apply()
            finish()
        }
    }
}
