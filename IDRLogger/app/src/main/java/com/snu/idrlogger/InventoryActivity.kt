package com.snu.idrlogger

import android.content.Context
import android.hardware.SensorManager
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class InventoryActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_inventory)
        val sm = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        findViewById<TextView>(R.id.tvInventory).text = SensorInventory.humanReadable(sm)
    }
}
