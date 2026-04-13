import io
import ipaddress
import logging
import os
import re
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, send_file
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("CSRGEN_SESSION_COOKIE_SECURE", "").lower() in {
    "1",
    "true",
    "yes",
}

_logger = logging.getLogger("csrgen")
if not _logger.handlers:
    logging.basicConfig(level=os.getenv("CSRGEN_LOG_LEVEL", "INFO").upper())


def _safe_download_basename(value: str, default: str = "certificate") -> str:
    """
    Best-effort sanitizer for filenames used in Content-Disposition.
    Prevents path traversal, CRLF header injection, and weird characters.
    """
    v = (value or "").strip()
    if not v:
        return default
    # Drop path separators and control chars
    v = v.replace("/", "_").replace("\\", "_")
    v = re.sub(r"[\r\n\t\0]", "_", v)
    # Allow a conservative set of characters
    v = re.sub(r"[^a-zA-Z0-9._-]", "_", v)
    v = v.lstrip(".")  # avoid hidden files / empty basename
    v = re.sub(r"_+", "_", v)
    v = v.strip("._-")
    if not v:
        return default
    return v[:80]


@app.after_request
def add_security_headers(resp):
    # Clickjacking + sniffing protection
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    # Limit referrer leakage
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # Disable powerful APIs by default
    resp.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    )
    # Basic CSP (no inline scripts used)
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "base-uri 'none'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "script-src 'self'",
    )

    # Only set HSTS when we're actually on HTTPS (or behind a proxy terminating TLS)
    is_https = request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"
    if is_https:
        resp.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate_csr():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Ungültige Anfrage."}), 400

    cn = (data.get("cn") or "").strip()
    o = (data.get("o") or "").strip()
    ou = (data.get("ou") or "").strip()
    c = (data.get("c") or "").strip()
    st = (data.get("st") or "").strip()
    l_val = (data.get("l") or "").strip()
    email = (data.get("email") or "").strip()
    key_size = int(data.get("key_size", 2048))
    cert_type = data.get("cert_type", "standard")
    san_names = data.get("san_names", [])

    if not cn:
        return jsonify({"error": "Common Name (CN) ist ein Pflichtfeld."}), 400

    if c and len(c) != 2:
        return jsonify({"error": "Ländercode muss genau 2 Zeichen lang sein (z.B. DE)."}), 400

    if key_size not in (2048, 4096):
        return jsonify({"error": "Schlüssellänge muss 2048 oder 4096 sein."}), 400

    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)

        name_attrs = []
        if cn:
            name_attrs.append(x509.NameAttribute(NameOID.COMMON_NAME, cn))
        if o:
            name_attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, o))
        if ou:
            name_attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, ou))
        if c:
            name_attrs.append(x509.NameAttribute(NameOID.COUNTRY_NAME, c.upper()))
        if st:
            name_attrs.append(x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, st))
        if l_val:
            name_attrs.append(x509.NameAttribute(NameOID.LOCALITY_NAME, l_val))
        if email:
            name_attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))

        subject = x509.Name(name_attrs)
        builder = x509.CertificateSigningRequestBuilder().subject_name(subject)

        if cert_type == "san" and san_names:
            sans = _build_san_list(cn, san_names)
            if sans:
                builder = builder.add_extension(
                    x509.SubjectAlternativeName(sans), critical=False
                )

        elif cert_type == "wildcard":
            sans = [x509.DNSName(cn)]
            if cn.startswith("*."):
                base = cn[2:]
                sans.append(x509.DNSName(base))
            builder = builder.add_extension(
                x509.SubjectAlternativeName(sans), critical=False
            )

        elif cert_type == "standard":
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False
            )

        csr = builder.sign(key, hashes.SHA256())

        csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()
        key_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        details = _extract_csr_details(csr)

        return jsonify({"csr": csr_pem, "key": key_pem, "cn": cn, "details": details})

    except Exception:
        _logger.exception("CSR generation failed")
        return jsonify({"error": "Fehler bei der Generierung."}), 500


@app.route("/api/convert-p12", methods=["POST"])
def convert_p12():
    key_file = request.files.get("key")
    cert_file = request.files.get("cert")
    chain_file = request.files.get("chain")
    password = request.form.get("password", "")
    key_password = request.form.get("key_password", "")
    target_format = (request.form.get("target_format", "p12") or "p12").lower()

    if not cert_file:
        return jsonify({"error": "Zertifikatsdatei wird benötigt."}), 400

    supported_formats = {"p12", "pfx", "cer_der", "cer_pem", "p7b"}
    if target_format not in supported_formats:
        return jsonify({"error": "Unbekanntes Zielformat."}), 400

    try:
        cert_data = cert_file.read()
        chain_data = chain_file.read() if chain_file else b""

        certificates = _load_certificates_from_data(cert_data)
        if not certificates:
            return jsonify({"error": "Zertifikat konnte nicht gelesen werden."}), 400
        certificate = certificates[0]

        chain_certs = _load_certificates_from_data(chain_data) if chain_data else []

        cn = ""
        try:
            cn = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        except (IndexError, Exception):
            pass
        base_filename = _safe_download_basename(cn or "certificate")

        if target_format in {"p12", "pfx"}:
            if not key_file:
                return jsonify({"error": "Für P12/PFX wird eine Schlüsseldatei benötigt."}), 400

            key_data = key_file.read()
            private_key = _load_private_key_from_data(
                key_data,
                key_password.encode() if key_password else None,
            )

            encryption = (
                serialization.BestAvailableEncryption(password.encode())
                if password
                else serialization.NoEncryption()
            )
            ext = "pfx" if target_format == "pfx" else "p12"
            bundle_data = pkcs12.serialize_key_and_certificates(
                name=base_filename.encode(),
                key=private_key,
                cert=certificate,
                cas=chain_certs or None,
                encryption_algorithm=encryption,
            )
            return send_file(
                io.BytesIO(bundle_data),
                mimetype="application/x-pkcs12",
                as_attachment=True,
                download_name=f"{base_filename}.{ext}",
            )

        if target_format == "cer_der":
            der_data = certificate.public_bytes(serialization.Encoding.DER)
            return send_file(
                io.BytesIO(der_data),
                mimetype="application/pkix-cert",
                as_attachment=True,
                download_name=f"{base_filename}.cer",
            )

        if target_format == "cer_pem":
            pem_data = certificate.public_bytes(serialization.Encoding.PEM)
            return send_file(
                io.BytesIO(pem_data),
                mimetype="application/x-pem-file",
                as_attachment=True,
                download_name=f"{base_filename}.cer",
            )

        if target_format == "p7b":
            p7b_certs = [certificate] + chain_certs
            p7b_data = pkcs7.serialize_certificates(
                p7b_certs,
                serialization.Encoding.DER,
            )
            return send_file(
                io.BytesIO(p7b_data),
                mimetype="application/x-pkcs7-certificates",
                as_attachment=True,
                download_name=f"{base_filename}.p7b",
            )

        return jsonify({"error": "Konvertierung nicht möglich."}), 400

    except ValueError:
        # e.g. wrong password, invalid key/cert formats
        _logger.exception("P12 conversion failed (value error)")
        return jsonify({"error": "Konvertierung fehlgeschlagen: Schlüssel/Zertifikat/Passwort prüfen."}), 400
    except Exception:
        _logger.exception("P12 conversion failed")
        return jsonify({"error": "Konvertierung fehlgeschlagen."}), 400


@app.route("/api/inspect", methods=["POST"])
def inspect_pem():
    data = request.get_json(silent=True)
    pem_text = (data.get("pem") or "").strip() if data else ""

    if not pem_text:
        return jsonify({"error": "Kein PEM-Inhalt übermittelt."}), 400

    pem_bytes = pem_text.encode()

    if "BEGIN CERTIFICATE REQUEST" in pem_text:
        try:
            csr = x509.load_pem_x509_csr(pem_bytes)
            details = _extract_csr_details(csr)
            return jsonify({"type": "csr", "details": details})
        except Exception:
            _logger.exception("Inspect CSR failed")
            return jsonify({"error": "CSR konnte nicht gelesen werden."}), 400

    elif "BEGIN CERTIFICATE" in pem_text:
        try:
            cert = x509.load_pem_x509_certificate(pem_bytes)
            details = _extract_cert_details(cert)
            return jsonify({"type": "certificate", "details": details})
        except Exception:
            _logger.exception("Inspect certificate failed")
            return jsonify({"error": "Zertifikat konnte nicht gelesen werden."}), 400

    else:
        return jsonify({"error": "Unbekanntes PEM-Format. Bitte CSR oder Zertifikat einfügen."}), 400


def _build_san_list(cn, san_names):
    seen = set()
    sans = []
    if cn:
        sans.append(x509.DNSName(cn))
        seen.add(cn.lower())
    for name in san_names:
        name = name.strip()
        if name and name.lower() not in seen:
            try:
                ip = ipaddress.ip_address(name)
                sans.append(x509.IPAddress(ip))
            except ValueError:
                sans.append(x509.DNSName(name))
            seen.add(name.lower())
    return sans


def _load_private_key_from_data(key_data, password):
    try:
        return serialization.load_pem_private_key(key_data, password=password)
    except ValueError:
        return serialization.load_der_private_key(key_data, password=password)


def _load_certificates_from_data(cert_data):
    if not cert_data:
        return []

    certificates = []
    if b"-----BEGIN CERTIFICATE-----" in cert_data:
        pem_blocks = re.findall(
            rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
            cert_data,
            flags=re.DOTALL,
        )
        for block in pem_blocks:
            certificates.append(x509.load_pem_x509_certificate(block))
    else:
        certificates.append(x509.load_der_x509_certificate(cert_data))
    return certificates


def _extract_csr_details(csr):
    subject = {}
    oid_labels = {
        "commonName": "Common Name",
        "organizationName": "Organisation",
        "organizationalUnitName": "Organisationseinheit",
        "countryName": "Land",
        "stateOrProvinceName": "Bundesland",
        "localityName": "Stadt",
        "emailAddress": "E-Mail",
    }
    for attr in csr.subject:
        label = oid_labels.get(attr.oid._name, attr.oid._name)
        subject[label] = attr.value

    sans = []
    try:
        san_ext = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        san_val = san_ext.value
        sans = [str(n) for n in san_val]
    except x509.ExtensionNotFound:
        pass

    return {
        "subject": subject,
        "sans": sans,
        "key_size": csr.public_key().key_size,
        "signature_algorithm": csr.signature_hash_algorithm.name if csr.signature_hash_algorithm else "unbekannt",
        "is_valid": csr.is_signature_valid,
    }


def _extract_cert_details(cert):
    subject = {}
    issuer = {}
    oid_labels = {
        "commonName": "Common Name",
        "organizationName": "Organisation",
        "organizationalUnitName": "Organisationseinheit",
        "countryName": "Land",
        "stateOrProvinceName": "Bundesland",
        "localityName": "Stadt",
        "emailAddress": "E-Mail",
    }

    for attr in cert.subject:
        label = oid_labels.get(attr.oid._name, attr.oid._name)
        subject[label] = attr.value

    for attr in cert.issuer:
        label = oid_labels.get(attr.oid._name, attr.oid._name)
        issuer[label] = attr.value

    sans = []
    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        san_val = san_ext.value
        sans = [str(n) for n in san_val]
    except x509.ExtensionNotFound:
        pass

    not_before = cert.not_valid_before_utc.strftime("%d.%m.%Y %H:%M UTC")
    not_after = cert.not_valid_after_utc.strftime("%d.%m.%Y %H:%M UTC")
    now = datetime.now(timezone.utc)
    is_expired = now > cert.not_valid_after_utc

    return {
        "subject": subject,
        "issuer": issuer,
        "sans": sans,
        "serial": format(cert.serial_number, "X"),
        "not_before": not_before,
        "not_after": not_after,
        "is_expired": is_expired,
        "key_size": cert.public_key().key_size,
        "signature_algorithm": cert.signature_hash_algorithm.name if cert.signature_hash_algorithm else "unbekannt",
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
