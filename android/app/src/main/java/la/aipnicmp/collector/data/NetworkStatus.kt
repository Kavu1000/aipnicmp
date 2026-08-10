package la.aipnicmp.collector.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import androidx.core.content.ContextCompat

/**
 * Whether this phone currently has usable internet.
 *
 * "Online" here means what WorkManager's `NetworkType.CONNECTED` constraint
 * means — the same condition that decides whether an upload runs. Anything
 * looser would tell the collector they are connected while the queue sits
 * untouched.
 *
 * VALIDATED matters as much as CONNECTED: a phone attached to a cell with no
 * working data path reports a network, and treating that as online is exactly
 * how a collector ends up believing their records went somewhere.
 */
object NetworkStatus {

    fun isOnline(context: Context): Boolean {
        val manager = ContextCompat.getSystemService(context, ConnectivityManager::class.java)
            ?: return false
        val capabilities = manager.getNetworkCapabilities(manager.activeNetwork) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    /**
     * Whether the active connection is the cellular one.
     *
     * The speed test exists to say what the *mobile network* delivers at a
     * place. Run it over wifi and it measures somebody's router, then files the
     * answer against the hexagon as though a tower had produced it — a village
     * hall with fibre would teach the model that its radio conditions imply
     * 40 Mbps. Better to skip the test than to record that.
     */
    fun isCellular(context: Context): Boolean {
        val manager = ContextCompat.getSystemService(context, ConnectivityManager::class.java)
            ?: return false
        val capabilities = manager.getNetworkCapabilities(manager.activeNetwork) ?: return false
        return capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    /**
     * Watch for changes, so the screen reflects reality rather than whatever was
     * true when it opened. Returns a handle the caller must release.
     */
    fun observe(context: Context, onChange: (Boolean) -> Unit): ConnectivityManager.NetworkCallback? {
        val manager = ContextCompat.getSystemService(context, ConnectivityManager::class.java)
            ?: return null

        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = onChange(isOnline(context))
            override fun onLost(network: Network) = onChange(isOnline(context))
            override fun onCapabilitiesChanged(
                network: Network,
                capabilities: NetworkCapabilities,
            ) = onChange(isOnline(context))
        }

        return try {
            manager.registerDefaultNetworkCallback(callback)
            callback
        } catch (_: SecurityException) {
            null
        }
    }

    fun stopObserving(context: Context, callback: ConnectivityManager.NetworkCallback?) {
        if (callback == null) return
        val manager = ContextCompat.getSystemService(context, ConnectivityManager::class.java)
        runCatching { manager?.unregisterNetworkCallback(callback) }
    }
}
