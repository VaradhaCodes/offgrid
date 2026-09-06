package com.snu.idrlogger.map

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Offline basemap plumbing (R6 §4–§5): the PMTiles archive is copied from assets to filesDir on first run (pmtiles://asset:// is not
 * supported), the Protomaps style is loaded with `__FILESDIR__` substituted, and our own sources and layers are injected into the
 * style JSON before MapLibre parses it. Layer ids and colours follow the design tokens of the handoff (§4).
 */
object MapAssets {
    const val PMTILES = "snu.pmtiles"
    // design tokens
    const val C_GROUND = "#101010"; const val C_BUILD_TOP = "#232323"; const val C_WATER = "#1F262B"; const val C_FIELD = "#151B16"; const val C_FIELD_EDGE = "#1C241D"
    const val C_GREEN = "#141A15"; const val C_LABEL = "#8C8C8C"; const val C_HALO = "#101010"
    const val C_LOCKED = "#9BE8C4"; const val C_DR = "#FFB454"; const val C_RELOCK = "#7FD3FF"; const val C_BAND = "#FF5A5F"; const val C_REVEAL = "#FFFFFF"

    val OUR_LAYER_IDS = listOf("idr_esri", "idr_features_green", "idr_features_water", "idr_features_sport", "idr_features_sport_line", "idr_campus_line",
        "idr_band_fill", "idr_band_line", "idr_ribbon", "idr_trail_lock", "idr_trail_dr", "idr_reveal", "idr_cone_4", "idr_cone_3", "idr_cone_2", "idr_cone_1",
        "idr_buildings_3d", "idr_labels_major", "idr_labels_minor")
    val HIDE_IN_SATELLITE_OURS = listOf("idr_features_green", "idr_features_water", "idr_features_sport", "idr_features_sport_line", "idr_buildings_3d", "idr_campus_line")

    fun pmtilesFile(ctx: Context): File = File(ctx.filesDir, PMTILES)

    /** Copies assets/map/snu.pmtiles to filesDir if missing or of a different size. Returns the file. */
    fun ensurePmtiles(ctx: Context): File {
        val out = pmtilesFile(ctx)
        val afd = try { ctx.assets.openFd("map/$PMTILES") } catch (t: Throwable) { null }
        val assetLen = afd?.length ?: -1L; afd?.close()
        if (out.exists() && (assetLen < 0 || out.length() == assetLen)) return out
        ctx.assets.open("map/$PMTILES").use { i -> out.outputStream().use { o -> i.copyTo(o, 1 shl 16) } }
        Log.i("IDR", "copied $PMTILES to ${out.absolutePath} (${out.length()} bytes)")
        return out
    }

    class StyleMeta(val roadIds: List<String>, val labelIds: List<String>, val landuseIds: List<String>, val waterIds: List<String>, val firstSymbol: String, val attribution: String)

    fun styleMeta(ctx: Context): StyleMeta {
        val m = JSONObject(ctx.assets.open("map/style_meta.json").bufferedReader().readText())
        fun ids(k: String): List<String> { val a = m.optJSONArray(k) ?: JSONArray(); return (0 until a.length()).map { a.getString(it) } }
        return StyleMeta(ids("road_layer_ids"), ids("label_layer_ids"), ids("landuse_layer_ids"), ids("water_layer_ids"), m.optString("first_symbol_layer_id", ""), m.optString("attribution", "© OpenStreetMap contributors"))
    }

    private fun emptyFc() = JSONObject().put("type", "FeatureCollection").put("features", JSONArray())
    private fun geojsonSrc(data: Any) = JSONObject().put("type", "geojson").put("data", data)

    /** Builds the full style JSON string for MapLibre (dark vector basemap + our layers; satellite layer present but hidden). */
    fun buildStyle(ctx: Context, meta: StyleMeta): String {
        val pm = ensurePmtiles(ctx)
        val text = ctx.assets.open("map/style.json").bufferedReader().readText().replace("__FILESDIR__", ctx.filesDir.absolutePath)
        val style = JSONObject(text)
        val sources = style.getJSONObject("sources")
        sources.put("idr_esri", JSONObject().put("type", "raster").put("tiles", JSONArray().put("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"))
            .put("tileSize", 256).put("maxzoom", 19).put("attribution", "Esri, Maxar, Earthstar Geographics"))
        sources.put("idr_buildings", geojsonSrc("asset://map/buildings.geojson"))
        sources.put("idr_campus", geojsonSrc("asset://map/campus.geojson"))
        sources.put("idr_features", geojsonSrc("asset://map/features.geojson"))
        sources.put("idr_labels", geojsonSrc("asset://map/labels.geojson"))
        for (id in listOf("idr_band", "idr_trail_lock", "idr_trail_dr", "idr_ribbon", "idr_reveal", "idr_cone")) sources.put(id, geojsonSrc(emptyFc()))

        val layers = style.getJSONArray("layers")
        val list = ArrayList<JSONObject>(); for (i in 0 until layers.length()) list.add(layers.getJSONObject(i))
        fun idx(id: String): Int = list.indexOfFirst { it.optString("id") == id }
        fun layer(id: String, type: String, source: String, paint: JSONObject, layout: JSONObject? = null, minzoom: Double? = null, filter: JSONArray? = null): JSONObject {
            val o = JSONObject().put("id", id).put("type", type).put("source", source).put("paint", paint)
            if (layout != null) o.put("layout", layout); if (minzoom != null) o.put("minzoom", minzoom); if (filter != null) o.put("filter", filter)
            return o
        }
        fun ja(vararg v: Any): JSONArray { val a = JSONArray(); for (x in v) a.put(x); return a }
        fun kindIs(vararg kinds: String): JSONArray { val a = ja("match", ja("get", "kind")); val k = JSONArray(); for (x in kinds) k.put(x); a.put(k); a.put(true); a.put(false); return a }

        // 1. satellite raster right above the background (hidden until toggled)
        val esri = layer("idr_esri", "raster", "idr_esri", JSONObject().put("raster-opacity", 1.0).put("raster-saturation", -0.25).put("raster-contrast", 0.05), JSONObject().put("visibility", "none"))
        val bgIdx = list.indexOfFirst { it.optString("type") == "background" }
        list.add(bgIdx + 1, esri)

        // 2. campus features under the roads: parks/green, water, sports fields with an edge
        val firstRoad = meta.roadIds.map { idx(it) }.filter { it >= 0 }.minOrNull() ?: list.size
        val feats = listOf(
            layer("idr_features_green", "fill", "idr_features", JSONObject().put("fill-color", C_GREEN), filter = kindIs("green", "grass"), minzoom = 13.0),
            layer("idr_features_water", "fill", "idr_features", JSONObject().put("fill-color", C_WATER), filter = ja("all", kindIs("water"), ja("==", ja("geometry-type"), "Polygon")), minzoom = 12.0),
            layer("idr_features_sport", "fill", "idr_features", JSONObject().put("fill-color", C_FIELD), filter = kindIs("sport"), minzoom = 14.0),
            layer("idr_features_sport_line", "line", "idr_features", JSONObject().put("line-color", C_FIELD_EDGE).put("line-width", 1.0), filter = kindIs("sport"), minzoom = 15.0),
            layer("idr_campus_line", "line", "idr_campus", JSONObject().put("line-color", "#2A2A2A").put("line-width", 1.2).put("line-dasharray", ja(3, 2)), minzoom = 12.0)
        )
        list.addAll(firstRoad, feats)

        // 3. ride overlays + 3-D buildings above every road layer and just below the first symbol layer that follows the roads
        //    (the Protomaps style has water labels before the roads; inserting there would hide the trail under the road fills)
        val lastRoad = meta.roadIds.map { idx(it) }.filter { it >= 0 }.maxOrNull() ?: -1
        val firstSym = list.indices.firstOrNull { i -> i > lastRoad && list[i].optString("type") == "symbol" } ?: list.size
        val dash = ja(8.0 / 3.0, 5.0 / 3.0)
        // ribbon width: 2 sigma metres -> px = w * 2^z / (156543.03 cos(lat)), minimum 4
        val cosLat = Math.cos(Math.toRadians(28.524))
        val ribbonWidth = ja("interpolate", ja("exponential", 2), ja("zoom"))
        for (z in listOf(12, 14, 15, 16, 17, 18, 19, 20, 22)) { val kz = Math.pow(2.0, z.toDouble()) / (156543.03 * cosLat); ribbonWidth.put(z); ribbonWidth.put(ja("max", 4, ja("*", ja("get", "w"), kz))) }
        val overlays = listOf(
            layer("idr_band_fill", "fill", "idr_band", JSONObject().put("fill-color", C_BAND).put("fill-opacity", 0.22).put("fill-pattern", "idr_hatch")),
            layer("idr_band_line", "line", "idr_band", JSONObject().put("line-color", C_BAND).put("line-opacity", 0.6).put("line-width", 1.5)),
            layer("idr_ribbon", "line", "idr_ribbon", JSONObject().put("line-color", C_DR).put("line-opacity", 0.18).put("line-width", ribbonWidth), JSONObject().put("line-cap", "round").put("line-join", "round")),
            layer("idr_trail_lock", "line", "idr_trail_lock", JSONObject().put("line-color", C_LOCKED).put("line-width", 3.0), JSONObject().put("line-cap", "round").put("line-join", "round")),
            layer("idr_trail_dr", "line", "idr_trail_dr", JSONObject().put("line-color", C_DR).put("line-width", 3.0).put("line-dasharray", dash), JSONObject().put("line-cap", "butt").put("line-join", "round")),
            layer("idr_reveal", "line", "idr_reveal", JSONObject().put("line-color", C_REVEAL).put("line-opacity", 0.0).put("line-width", 2.0).put("line-dasharray", ja(0.1, 2.2)), JSONObject().put("line-cap", "round").put("line-join", "round")),
            layer("idr_cone_4", "fill", "idr_cone", JSONObject().put("fill-color", C_LOCKED).put("fill-opacity", 0.06), filter = ja("==", ja("get", "ring"), 4)),
            layer("idr_cone_3", "fill", "idr_cone", JSONObject().put("fill-color", C_LOCKED).put("fill-opacity", 0.10), filter = ja("==", ja("get", "ring"), 3)),
            layer("idr_cone_2", "fill", "idr_cone", JSONObject().put("fill-color", C_LOCKED).put("fill-opacity", 0.12), filter = ja("==", ja("get", "ring"), 2)),
            layer("idr_cone_1", "fill", "idr_cone", JSONObject().put("fill-color", C_LOCKED).put("fill-opacity", 0.14), filter = ja("==", ja("get", "ring"), 1)),
            layer("idr_buildings_3d", "fill-extrusion", "idr_buildings", JSONObject().put("fill-extrusion-color", C_BUILD_TOP).put("fill-extrusion-height", ja("get", "render_height"))
                .put("fill-extrusion-base", ja("get", "render_min_height")).put("fill-extrusion-opacity", 0.95).put("fill-extrusion-vertical-gradient", true), minzoom = 15.0)
        )
        list.addAll(firstSym, overlays)

        // 4. our building / place labels on top
        fun labelLayer(id: String, minKey: Int, maxKey: Int, minzoom: Double, size: JSONArray) = layer(id, "symbol", "idr_labels",
            JSONObject().put("text-color", C_LABEL).put("text-halo-color", C_HALO).put("text-halo-width", 1.2),
            JSONObject().put("text-field", ja("get", "name")).put("text-font", ja("Noto Sans Medium")).put("text-size", size).put("symbol-sort-key", ja("get", "sort_key"))
                .put("text-max-width", 8).put("text-padding", 6).put("text-anchor", "center").put("text-allow-overlap", false),
            minzoom = minzoom, filter = ja("all", ja(">=", ja("get", "sort_key"), minKey), ja("<=", ja("get", "sort_key"), maxKey)))
        list.add(labelLayer("idr_labels_major", 0, 20, 15.5, ja("interpolate", ja("linear"), ja("zoom"), 15, 11, 18, 13.5)))
        list.add(labelLayer("idr_labels_minor", 21, 99, 16.5, ja("interpolate", ja("linear"), ja("zoom"), 16, 10, 18, 12)))

        val newLayers = JSONArray(); for (l in list) newLayers.put(l)
        style.put("layers", newLayers)
        Log.i("IDR", "style built: ${list.size} layers, pmtiles ${pm.length()} bytes")
        return style.toString()
    }
}
