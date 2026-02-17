# CSRgen – Certificate Signing Request Generator

A Docker-based web application for creating TLS/SSL Certificate Signing Requests (CSR) with a clean, modern UI. No OpenSSL knowledge required.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

- **CSR & Private Key Generation** – Create private key and CSR in one step
- **Standard Certificates** – Single domain certificates
- **Multi-Domain (SAN)** – Multiple domains in a single certificate
- **Wildcard Certificates** – `*.domain.com` for all subdomains
- **P12 Conversion** – Convert key + certificate to PKCS#12 format
- **CSR / Certificate Inspector** – View contents of CSR and certificate files
- **Key Size Selection** – 2048 or 4096 bit
- **Dark Mode** – Easy on the eyes
- **Security First** – Private keys are never stored on the server

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python 3.12, Flask |
| Cryptography | Python `cryptography` library |
| WSGI Server | Gunicorn |
| Frontend | Vanilla HTML / CSS / JS |
| Container | Docker |

---

## Quick Start

```bash
git clone https://github.com/nycon/csrgen.git
cd csrgen
docker compose up -d
```

Open **http://localhost:8443** in your browser.

---

## Setup Guides

- [macOS](#macos-setup)
- [Windows](#windows-setup)
- [Linux Server (Production with Nginx + SSL)](#linux-production-setup)

---

## macOS Setup

### Prerequisites

Install Docker Desktop for macOS:

1. Download from [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
2. Open the `.dmg` file and drag Docker to Applications
3. Launch Docker Desktop and wait until it shows **"Docker is running"**

Alternatively, install via Homebrew:

```bash
brew install --cask docker
```

### Install & Run

```bash
git clone https://github.com/nycon/csrgen.git
cd csrgen
docker compose up -d
```

Open **http://localhost:8443** in your browser.

### Stop

```bash
docker compose down
```

### Troubleshooting (macOS)

**Port 5000 already in use:**
macOS Monterey+ uses port 5000 for AirPlay Receiver. CSRgen already uses port 8443 to avoid this. If port 8443 is also in use, change it in `docker-compose.yml`:

```yaml
ports:
  - "9090:5000"   # change 9090 to any free port
```

---

## Windows Setup

### Prerequisites

1. **Install Docker Desktop for Windows:**
   - Download from [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
   - Run the installer and follow the prompts
   - Ensure **WSL 2** backend is selected during installation (recommended)
   - Restart your computer if prompted

2. **Enable WSL 2 (if not already):**
   Open PowerShell as Administrator:

   ```powershell
   wsl --install
   ```

   Restart your computer after installation.

3. **Verify Docker is running:**

   ```powershell
   docker --version
   docker compose version
   ```

### Install & Run

Open PowerShell or Windows Terminal:

```powershell
git clone https://github.com/nycon/csrgen.git
cd csrgen
docker compose up -d
```

Open **http://localhost:8443** in your browser.

### Stop

```powershell
docker compose down
```

### Run on Windows startup (optional)

Docker Desktop can be configured to start on login:
- Open Docker Desktop → Settings → General → **Start Docker Desktop when you sign in**

The container will restart automatically thanks to `restart: unless-stopped`.

---

## Linux Production Setup

This guide covers a full production deployment on a Linux server with:

- Docker & Docker Compose
- Nginx reverse proxy
- Free SSL/TLS certificate via Let's Encrypt
- Automatic certificate renewal
- Firewall configuration

### 1. Server Prerequisites

Tested on: Ubuntu 22.04 / 24.04 LTS, Debian 12, Rocky Linux 9

```bash
# Update system
sudo apt update && sudo apt upgrade -y       # Debian/Ubuntu
# sudo dnf update -y                          # Rocky/RHEL

# Install required packages
sudo apt install -y ca-certificates curl gnupg git
```

### 2. Install Docker

```bash
# Add Docker's official GPG key and repository
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add your user to the docker group (log out and back in after this)
sudo usermod -aG docker $USER
```

Verify installation:

```bash
docker --version
docker compose version
```

### 3. Clone & Start CSRgen

```bash
cd /opt
sudo git clone https://github.com/nycon/csrgen.git
sudo chown -R $USER:$USER /opt/csrgen
cd /opt/csrgen
docker compose up -d
```

Verify the container is running:

```bash
docker compose ps
curl -s http://localhost:8443 | head -5
```

### 4. Install & Configure Nginx

```bash
sudo apt install -y nginx
```

Create the Nginx site configuration:

```bash
sudo tee /etc/nginx/sites-available/csrgen <<'EOF'
server {
    listen 80;
    server_name csrgen.example.com;   # <-- Replace with your domain

    # Redirect HTTP to HTTPS (enabled after SSL setup)
    location / {
        return 301 https://$host$request_uri;
    }

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
}

server {
    listen 443 ssl http2;
    server_name csrgen.example.com;   # <-- Replace with your domain

    # SSL certificates (will be created in step 5)
    ssl_certificate     /etc/letsencrypt/live/csrgen.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/csrgen.example.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Upload limit for P12 conversion
    client_max_body_size 5M;

    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

Enable the site:

```bash
sudo ln -sf /etc/nginx/sites-available/csrgen /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

For the initial SSL setup, temporarily comment out the `server` block listening on 443 so Nginx can start:

```bash
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx
```

### 5. SSL Certificate with Let's Encrypt

Install Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

Obtain the certificate (replace `csrgen.example.com` with your domain):

```bash
sudo certbot --nginx -d csrgen.example.com --non-interactive --agree-tos -m your@email.com
```

Certbot will automatically configure Nginx with the certificate. Verify:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Now uncomment the full HTTPS server block if it was commented out, and reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 6. Automatic Certificate Renewal

Certbot installs a systemd timer automatically. Verify:

```bash
sudo systemctl status certbot.timer
```

Test renewal:

```bash
sudo certbot renew --dry-run
```

### 7. Firewall Configuration

#### UFW (Ubuntu/Debian)

```bash
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP (for Let's Encrypt redirect)
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
sudo ufw status
```

#### firewalld (Rocky/RHEL)

```bash
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
sudo firewall-cmd --list-all
```

### 8. Verify Production Setup

```bash
# Check container status
docker compose -f /opt/csrgen/docker-compose.yml ps

# Check Nginx status
sudo systemctl status nginx

# Test HTTPS
curl -I https://csrgen.example.com
```

Visit **https://csrgen.example.com** in your browser. You should see a valid SSL certificate and the CSRgen interface.

---

## Updating

```bash
cd /opt/csrgen               # or wherever you cloned the repo
git pull
docker compose up -d --build
```

---

## Configuration

### Changing the Port

Edit `docker-compose.yml`:

```yaml
ports:
  - "YOUR_PORT:5000"
```

Then restart:

```bash
docker compose up -d
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PYTHONUNBUFFERED` | `1` | Ensures real-time log output |

---

## Security

- **No storage** – Private keys are generated in memory and sent directly to the browser. No files are ever written to disk.
- **Read-only filesystem** – The container runs with a read-only root filesystem.
- **Non-root** – The application runs as an unprivileged user inside the container.
- **No new privileges** – The container cannot gain additional privileges.
- **Upload limit** – File uploads are limited to 5 MB.

---

## Development

### Run locally without Docker

```bash
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# .\venv\Scripts\activate       # Windows PowerShell
pip install -r requirements.txt
python app.py
```

The development server starts at **http://localhost:5000**.

### Project Structure

```
csrgen/
├── app.py                  # Flask backend (CSR generation, P12, inspect)
├── templates/
│   └── index.html          # Main HTML template
├── static/
│   ├── css/
│   │   └── style.css       # Styles with dark mode support
│   └── js/
│       └── app.js          # Frontend logic
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Docker Compose configuration
├── requirements.txt        # Python dependencies
└── README.md
```

---

## License

MIT
