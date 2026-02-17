import io
import ipaddress
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, send_file
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit


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

    except Exception as exc:
        return jsonify({"error": f"Fehler bei der Generierung: {exc}"}), 500


@app.route("/api/convert-p12", methods=["POST"])
def convert_p12():
    key_file = request.files.get("key")
    cert_file = request.files.get("cert")
    password = request.form.get("password", "")

    if not key_file or not cert_file:
        return jsonify({"error": "Schlüssel- und Zertifikatsdatei werden benötigt."}), 400

    try:
        key_data = key_file.read()
        cert_data = cert_file.read()

        private_key = serialization.load_pem_private_key(key_data, password=None)
        certificate = x509.load_pem_x509_certificate(cert_data)

        encryption = (
            serialization.BestAvailableEncryption(password.encode())
            if password
            else serialization.NoEncryption()
        )

        p12_data = pkcs12.serialize_key_and_certificates(
            name=None,
            key=private_key,
            cert=certificate,
            cas=None,
            encryption_algorithm=encryption,
        )

        cn = ""
        try:
            cn = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        except (IndexError, Exception):
            pass
        filename = f"{cn or 'certificate'}.p12"

        return send_file(
            io.BytesIO(p12_data),
            mimetype="application/x-pkcs12",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as exc:
        return jsonify({"error": f"Konvertierungsfehler: {exc}"}), 400


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
        except Exception as exc:
            return jsonify({"error": f"CSR konnte nicht gelesen werden: {exc}"}), 400

    elif "BEGIN CERTIFICATE" in pem_text:
        try:
            cert = x509.load_pem_x509_certificate(pem_bytes)
            details = _extract_cert_details(cert)
            return jsonify({"type": "certificate", "details": details})
        except Exception as exc:
            return jsonify({"error": f"Zertifikat konnte nicht gelesen werden: {exc}"}), 400

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
