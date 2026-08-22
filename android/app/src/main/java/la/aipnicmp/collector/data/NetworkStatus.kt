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

        // Every network, not just the active one.
        //
        // Android names one network "active", and when a phone is attached to
        // wifi that has stopped working it can go on naming that one — attached
        // but unvalidated — while mobile data carries every request perfectly
        // well. Asking only the active network then reports a phone as offline
        // in the middle of a town, and each reading it takes is filed as
        // "recorded with no internet" moments before it uploads successfully
        // over the connection that was there all along.
        //
        // The question this answers is whether anything can reach the server,
        // so it asks all of them and takes the best answer.
        return manager.allNetworks.any { network ->
            val capabilities = manager.getNetworkCapabilities(network)
            capabilities != null &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        }
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

        // Same reasoning as isOnline, with the opposite emphasis: a working
        // cellular path must be found specifically, because a throughput test
        // run over wifi measures somebody's router and files the answer against
        // a hexagon as though a tower produced it. Wifi being present is not a
        // reason to skip the test — wifi being the thing measured is.
        return manager.allNetworks.any { network ->
            val capabilities = manager.getNetworkCapabilities(network)
            capabilities != null &&
                capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        }
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
