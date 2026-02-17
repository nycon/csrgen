# CSRgen – Zertifikatsanfragen einfach erstellen

CSRgen ist eine Docker-basierte Webanwendung zur einfachen Erstellung von TLS/SSL Certificate Signing Requests (CSR). Kein OpenSSL-Wissen erforderlich.

## Funktionen

- **CSR & Schlüssel generieren** – Privaten Schlüssel und CSR in einem Schritt erstellen
- **Standard-Zertifikate** – Für einzelne Domains
- **Multi-Domain (SAN)** – Mehrere Domains in einem Zertifikat
- **Wildcard-Zertifikate** – `*.domain.com` für alle Subdomains
- **P12-Konvertierung** – Schlüssel + Zertifikat in PKCS#12 konvertieren
- **CSR / Zertifikat prüfen** – Inhalte von CSR und Zertifikaten anzeigen
- **Schlüssellänge wählbar** – 2048 oder 4096 Bit
- **Dark Mode** – Augenfreundliches Design

## Schnellstart

### Mit Docker Compose (empfohlen)

```bash
docker compose up -d
```

Die Anwendung ist dann unter **http://localhost:5000** erreichbar.

### Mit Docker Run

```bash
docker build -t csrgen .
docker run -d -p 5000:5000 --name csrgen csrgen
```

### Stoppen

```bash
docker compose down
```

## Sicherheit

- **Keine Speicherung** – Private Schlüssel werden ausschließlich im Arbeitsspeicher erzeugt und direkt an den Browser gesendet. Es werden keine Dateien auf dem Server gespeichert.
- **Read-Only Filesystem** – Der Container läuft mit schreibgeschütztem Dateisystem.
- **Kein Root** – Die Anwendung läuft als unprivilegierter Benutzer.

## Technologie

| Komponente | Technologie |
|---|---|
| Backend | Python 3.12, Flask |
| Kryptographie | Python `cryptography` Library |
| WSGI-Server | Gunicorn |
| Frontend | Vanilla HTML/CSS/JS |
| Container | Docker |

## Lokale Entwicklung (ohne Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Lizenz

MIT
