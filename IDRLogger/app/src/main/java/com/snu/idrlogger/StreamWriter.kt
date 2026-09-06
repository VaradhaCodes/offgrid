package com.snu.idrlogger

import java.io.BufferedWriter
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStreamWriter
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/**
 * One CSV stream. Producers (sensor / GNSS callback threads) only ever touch the
 * lock-free queue; a single writer thread owned by [StreamSet] drains every queue,
 * writes through a 64 KB buffer, flushes once a second and fsyncs on stop.
 *
 * Timing statistics are kept as a coarse histogram of inter-sample dt so a 20 minute
 * 500 Hz session costs ~56 KB per stream instead of 4.8 MB of retained longs.
 */
class StreamWriter(
    dir: File,
    val name: String,
    private val header: String,
    private val queueCap: Int = 400_000
) {
    val file: File = File(dir, "$name.csv")

    private val queue = ConcurrentLinkedQueue<String>()
    private val queued = AtomicInteger(0)

    /** rows handed to the queue (not necessarily flushed yet) */
    val rows = AtomicLong(0)
    /** rows discarded because the queue hit [queueCap] */
    val dropped = AtomicLong(0)

    /** rolling counter used by the UI to show achieved Hz */
    val sinceTick = AtomicLong(0)
    @Volatile var hz: Double = 0.0

    @Volatile var lastTs: Long = 0L      // last timestamp seen, ns (0 = none yet)
    @Volatile var firstTs: Long = 0L
    private val hist = IntArray(N_BUCKETS)
    private var dtCount = 0L
    private var gaps50 = 0L
    private var maxDt = 0L

    private var out: FileOutputStream? = null
    private var w: BufferedWriter? = null

    fun open() {
        val fos = FileOutputStream(file)
        val bw = BufferedWriter(OutputStreamWriter(fos, Charsets.UTF_8), 65536)
        bw.write(header); bw.write("\n")
        out = fos; w = bw
    }

    /**
     * Enqueue one row. [tNs] is the event's own timestamp (elapsedRealtime base) and is
     * used only for the dt statistics; pass 0 for streams that have no natural cadence.
     */
    fun add(tNs: Long, line: String) {
        if (queued.get() >= queueCap) { dropped.incrementAndGet(); return }
        queue.add(line)
        queued.incrementAndGet()
        rows.incrementAndGet()
        sinceTick.incrementAndGet()
        if (tNs > 0) {
            val prev = lastTs
            if (prev == 0L) firstTs = tNs else if (tNs > prev) recordDt(tNs - prev)
            lastTs = tNs
        }
    }

    // Only ever called from the producer of this stream (single producer per stream).
    private fun recordDt(dtNs: Long) {
        val us = dtNs / 1000
        val b = bucketOf(us)
        hist[b] = hist[b] + 1
        dtCount++
        if (dtNs > maxDt) maxDt = dtNs
        if (dtNs > 50_000_000L) gaps50++
    }

    /** Drains up to [max] rows. Returns how many were written. Writer thread only. */
    fun drain(max: Int): Int {
        val bw = w ?: return 0
        var n = 0
        while (n < max) {
            val s = queue.poll() ?: break
            queued.decrementAndGet()
            bw.write(s); bw.write("\n")
            n++
        }
        return n
    }

    fun flush() { w?.flush() }

    fun closeAndSync() {
        try {
            while (true) { if (drain(20_000) == 0) break }
            w?.flush()
            out?.fd?.sync()
        } catch (_: Throwable) {
        } finally {
            try { w?.close() } catch (_: Throwable) {}
            w = null; out = null
        }
    }

    fun tick(dtSec: Double) {
        val c = sinceTick.getAndSet(0)
        hz = if (dtSec > 0) c / dtSec else 0.0
    }

    fun medianDtMs(): Double = percentileDtMs(0.50)
    fun p99DtMs(): Double = percentileDtMs(0.99)
    fun gapsOver50ms(): Long = gaps50
    fun maxDtMs(): Double = maxDt / 1e6
    fun dtSamples(): Long = dtCount

    private fun percentileDtMs(p: Double): Double {
        if (dtCount == 0L) return Double.NaN
        val target = (dtCount * p).toLong().coerceAtLeast(1L)
        var cum = 0L
        for (b in hist.indices) {
            cum += hist[b]
            if (cum >= target) return bucketMidUs(b) / 1000.0
        }
        return bucketMidUs(N_BUCKETS - 1) / 1000.0
    }

    companion object {
        // 0..100 ms in 25 us steps, then 0.1..10 s in 1 ms steps, then one overflow bucket.
        private const val N_BUCKETS = 14001
        private fun bucketOf(us: Long): Int = when {
            us <= 0L -> 0
            us < 100_000L -> (us / 25L).toInt()
            us < 10_000_000L -> 4000 + (us / 1000L).toInt()
            else -> 14000
        }
        private fun bucketMidUs(b: Int): Double = when {
            b < 4000 -> b * 25.0 + 12.5
            b < 14000 -> (b - 4000) * 1000.0 + 500.0
            else -> 10_000_000.0
        }
    }
}

/**
 * Owns every [StreamWriter] of a session plus the single writer thread.
 */
class StreamSet(private val dir: File) {
    private val streams = LinkedHashMap<String, StreamWriter>()
    @Volatile private var running = false
    private var thread: Thread? = null

    fun create(name: String, header: String, queueCap: Int = 400_000): StreamWriter {
        val s = StreamWriter(dir, name, header, queueCap)
        s.open()
        streams[name] = s
        return s
    }

    fun all(): Collection<StreamWriter> = streams.values
    operator fun get(name: String): StreamWriter? = streams[name]

    fun totalDropped(): Long = streams.values.sumOf { it.dropped.get() }
    fun totalRows(): Long = streams.values.sumOf { it.rows.get() }

    fun start() {
        running = true
        val t = Thread({
            var lastFlush = System.nanoTime()
            while (running) {
                var moved = 0
                for (s in streams.values) moved += s.drain(4096)
                val now = System.nanoTime()
                if (now - lastFlush > 1_000_000_000L) {
                    for (s in streams.values) s.flush()
                    lastFlush = now
                }
                if (moved == 0) {
                    try { Thread.sleep(20) } catch (_: InterruptedException) { break }
                }
            }
        }, "idr-writer")
        t.priority = Thread.NORM_PRIORITY + 1
        t.start()
        thread = t
    }

    fun stopAndClose() {
        running = false
        try { thread?.join(4000) } catch (_: InterruptedException) {}
        for (s in streams.values) s.closeAndSync()
    }

    /** Recompute achieved Hz for every stream. */
    fun tickRates(dtSec: Double) { for (s in streams.values) s.tick(dtSec) }
}
