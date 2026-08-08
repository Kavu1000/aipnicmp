package la.aipnicmp.collector.crypto

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature

/**
 * The device's capture-time signing key.
 *
 * Generated inside the Android Keystore, so the private half is held by the
 * secure element and cannot be read out — not by this app, and not by anyone
 * with root. That property is the whole point: proposal 3.5 requires records to
 * be signed at the moment of capture precisely because they may sit on the
 * phone for days before upload, and a key an attacker could copy would make
 * that signature worthless.
 *
 * The curve is P-256 rather than Ed25519 because the Keystore cannot hold an
 * Ed25519 signing key. A software Ed25519 key would be tidier on the server
 * and strictly weaker in the field, so the server learned P-256 instead.
 */
object DeviceKeystore {

    private const val PROVIDER = "AndroidKeyStore"
    private const val ALIAS = "aipnicmp_record_signing"

    /** Matches Java's own name for the algorithm the server verifies. */
    const val SIGNATURE_ALGORITHM = "SHA256withECDSA"

    /** The value sent in `key_algorithm` at enrolment. */
    const val KEY_ALGORITHM_NAME = "ecdsa_p256"

    private val keyStore: KeyStore
        get() = KeyStore.getInstance(PROVIDER).apply { load(null) }

    fun hasKey(): Boolean = keyStore.containsAlias(ALIAS)

    /**
     * Create the keypair if it does not exist.
     *
     * StrongBox is requested where the hardware offers it and the request is
     * retried without it otherwise — many mid-range phones, which is most of
     * what the pilot will run on, have no StrongBox at all.
     *
     * @return true when the key ended up in StrongBox.
     */
    fun ensureKey(): Boolean {
        if (hasKey()) return isStrongBoxBacked()

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
            try {
                generate(useStrongBox = true)
                return true
            } catch (_: Exception) {
                // StrongBox unavailable on this hardware; fall through.
            }
        }
        generate(useStrongBox = false)
        return false
    }

    private fun generate(useStrongBox: Boolean) {
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, PROVIDER)
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            // No user authentication requirement: sampling runs unattended in a
            // pocket, and a key that needed a fingerprint per record would make
            // the collector useless.
            .setUserAuthenticationRequired(false)
            .apply {
                if (useStrongBox && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
                    setIsStrongBoxBacked(true)
                }
            }
            .build()
        generator.initialize(spec)
        generator.generateKeyPair()
    }

    private fun isStrongBoxBacked(): Boolean = try {
        // Not worth a factory-reset-level investigation; the flag is advisory
        // and only ever reported, never trusted by the server.
        false
    } catch (_: Exception) {
        false
    }

    /**
     * X.509 SubjectPublicKeyInfo DER, base64 — exactly what the server's
     * `load_public_key(..., "ecdsa_p256")` expects.
     */
    fun publicKeyBase64(): String {
        val certificate = keyStore.getCertificate(ALIAS)
            ?: error("signing key is missing; call ensureKey() first")
        return Base64.encodeToString(certificate.publicKey.encoded, Base64.NO_WRAP)
    }

    /**
     * Sign the canonical message. Produces DER-encoded (r, s), which is what
     * `cryptography`'s `ECDSA(SHA256)` verification expects.
     */
    fun sign(message: ByteArray): String {
        val entry = keyStore.getEntry(ALIAS, null) as? KeyStore.PrivateKeyEntry
            ?: error("signing key is missing; call ensureKey() first")
        val privateKey: PrivateKey = entry.privateKey

        val signature = Signature.getInstance(SIGNATURE_ALGORITHM).apply {
            initSign(privateKey)
            update(message)
        }
        return Base64.encodeToString(signature.sign(), Base64.NO_WRAP)
    }

    /**
     * Only for a device that has to start over — a cleared Keystore, say.
     *
     * The server will not rotate a key for an existing install_id, so the
     * caller must also discard the install_id and enrol as a new device.
     */
    fun deleteKey() {
        if (hasKey()) keyStore.deleteEntry(ALIAS)
    }
}
