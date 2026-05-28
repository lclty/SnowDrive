# ❄️ SnowDrive

 [简体中文](README.md) | English

**Secure Remote File Access System** —— A lightweight NAS solution based on Python/Flask, deployable with a single Docker command.

  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/flask-3.1-green.svg" alt="Flask">
  <img src="https://img.shields.io/badge/license-MIT-orange.svg" alt="License">
  <img src="https://img.shields.io/badge/docker-supported-brightgreen.svg" alt="Docker">

## 🌐 Online Experience

- 🏠 Homepage: [snowdrive.lclty.cn](https://snowdrive.lclty.cn)
- 🎮 Live Demo: [snowdrive.lclty.cn/demo](https://snowdrive.lclty.cn/demo)

## ✨ Features

- 🔐 **Secure Authentication** —— Username + Password + Mandatory Two-Factor Authentication (2FA)
  - TOTP dynamic verification codes (compatible with Microsoft Authenticator, Google Authenticator, etc.)
  - WebAuthn/Passkey support (fingerprint, facial recognition, Windows Hello, YubiKey, etc.)
- 📁 **Full File Management** —— Browse, upload, download, create files/folders, copy, move, rename, delete
- 🌐 **Remote Download** —— Download remote files to the server by pasting a URL; background tasks track progress in real time
- 📦 **Batch Operations** —— Multi-select files for batch download (automatic ZIP packaging), drag-and-drop upload
- 🎨 **Elegant UI** —— Responsive design, light/dark theme switching, mobile-friendly
- 🔒 **Fully Localized Assets** —— CSS/JS/FontAwesome are all local, zero external CDN dependencies
- 👤 **Single-User Mode** —— One global account; guided registration on first visit, ideal for personal/home use
- 💾 **Persistent Storage** —— Database and avatar files are stored on external Volumes; no data loss on container upgrades or rebuilds

![Screenshot](image.png)

## 🚀 Quick Start

### Pull from Docker Hub (Recommended)

```bash
docker pull lclty/snowdrive:latest

docker run -d \
  --name snowdrive \
  -p 8080:8080 \
  -v /your/data/path:/data \
  -v /your/userdata/path:/userdata \
  -e SNOWDRIVE_SECRET_KEY=your-random-secret-string \
  lclty/snowdrive:latest
```

**💡 For users in Mainland China**: If pulling from Docker Hub is slow or fails, try pulling through a proxy, or download the image from the [Releases](https://github.com/lclty/snowdrive/releases) page and import it offline:

```bash
cd /path/to/images
docker load -i snowdrive.tar

docker run -d \
  --name snowdrive \
  -p 8080:8080 \
  -v /your/data/path:/data \
  -v /your/userdata/path:/userdata \
  -e SNOWDRIVE_SECRET_KEY=your-random-secret-string \
  snowdrive:latest
```


## 🔨 Local Build

Advantages of building with Docker:
- **Environment isolation** —— Does not pollute the host Python environment, no need to manually install dependencies
- **One-click deployment** —— All dependencies are packaged in the image, running consistently across platforms
- **Easy management** —— Start, stop, upgrade, and rollback via Docker commands

Don't have Docker? Visit the [Docker official website](https://www.docker.com/) to download Docker Desktop (Windows/macOS) or install Docker Engine (Linux).

### 1. Docker Compose Deployment (Recommended)

```bash
# Clone the repository
git clone https://github.com/lclty/snowdrive.git
cd snowdrive

# Edit docker-compose.yml, modify mount paths and secret key
# Change ./data in volumes to the actual directory you want to share
# Change SNOWDRIVE_SECRET_KEY to a random string

docker compose up -d --build
```

> If you need a proxy to pull the base image during build, uncomment the `args` section in `docker-compose.yml` and fill in the proxy address.

### 2. Docker Command Deployment

```bash
# Clone the repository
git clone https://github.com/lclty/snowdrive.git
cd snowdrive

# Build the image
docker build -t snowdrive .

# Run the container
docker run -d \
  --name snowdrive \
  -p 8080:8080 \
  -v /your/local/data:/data \
  -v $(pwd)/userdata:/userdata \
  -e SNOWDRIVE_SECRET_KEY=your-random-secret \
  snowdrive
```


## 🌐 How to Access

### Local Access

Open your browser and visit **http://localhost:8080**

On the first visit, you will be guided to create an administrator account and set up 2FA (TOTP and/or WebAuthn/Passkey).

> ⚠️ **Note**: Due to browser security policies, WebAuthn/Passkey is only available under the following conditions:
> - `http://localhost` (local development)
> - `https://` (production HTTPS)
>
> When accessing via plain HTTP (non-localhost), only TOTP verification is available.

### Public Access (Nginx Reverse Proxy)

Below is a template for an Nginx HTTPS reverse proxy configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com; # Replace with your domain
    return 302 https://$host$request_uri;
}

server {
    # Check your NGINX version first with 'nginx -v'
    ## If your NGINX version < 1.25.1:
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    ## If your NGINX version >= 1.25.1:
    #listen 443 ssl;
    #listen [::]:443 ssl;
    #http2 on;

    # To enable HTTP/3, uncomment the lines below
    # Make sure your NGINX build supports HTTP/3 before enabling
    #listen 443 quic;
    #listen [::]:443 quic;
    #add_header Alt-Svc 'h3=":443"; ma=86400';

    server_name your-domain.com; # Replace with your domain

    # SSL certificates (replace with your actual certificate paths)
    # You can refer to https://zhuanlan.zhihu.com/p/347064501 to apply for SSL certificates using acme.sh
    ssl_certificate     /path/to/your/fullchain.pem;
    ssl_certificate_key /path/to/your/privkey.pem;

    # Security configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 0;   # No upload size limit

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

After modifying the configuration file, restart your NGINX or reload the Docker container running NGINX.


## 📋 2FA Reset

If you lose your 2FA device (new computer, new phone, lost secret key, etc.), you can force a reset via the CLI:

```bash
docker exec -it snowdrive reset-2fa <username> <password>
```

After verifying the password, the user's 2FA will be cleared and will be forced to set it up again on the next login.


## 🔧 Environment Variables

| Variable | Description | Default |
|------|------|--------|
| `SNOWDRIVE_SECRET_KEY` | JWT signing key (**must be changed in production**) | Randomly generated |
| `SNOWDRIVE_SESSION_DAYS` | Login session validity (days) | `7` |
| `TZ` | Container timezone | `Asia/Shanghai` |
| `HTTP_PROXY` | HTTP proxy inside the container (used for remote download outbound requests) | — |
| `HTTPS_PROXY` | HTTPS proxy inside the container (used for remote download outbound requests) | — |


## 🛡️ Security Notes

- **Be sure to change `SNOWDRIVE_SECRET_KEY`** to a sufficiently long random string (you can generate one with `openssl rand -hex 32`)
- **HTTPS is strongly recommended**, used with Nginx/Caddy reverse proxy; otherwise passwords are transmitted in plaintext and WebAuthn will be unavailable
- Passwords are stored using **bcrypt** hashing, which is irreversible
- Sessions use **httpOnly Secure Cookie + JWT** dual verification; JWT tokens are SHA-256 hashed before being stored in the database
- All file operations have **path traversal protection** (`safe_join_path` restricts operations within the `/data` directory)
- Sensitive operations (changing password, deleting 2FA methods) require re-verification of the current password


## 🏗️ Tech Stack

| Layer | Technology |
|------|------|
| Backend Framework | Python 3.12 + Flask 3.1 |
| Database | SQLite (stored in `/userdata/snowdrive.db`) |
| Authentication | bcrypt + PyJWT + Cookie |
| 2FA | pyotp (TOTP) + webauthn (WebAuthn/Passkey) |
| Frontend | Jinja2 templates + Vanilla JavaScript + CSS3 |
| Icons | FontAwesome 6 (local offline) |
| Containerization | Docker + Docker Compose |


## 📁 Project Structure

```
SnowDrive/
├── app/
│   ├── main.py              # Flask application entry point & blueprint registration
│   ├── config.py            # Configuration class (paths, keys, parameters)
│   ├── auth.py              # Authentication blueprint (registration/login/2FA setup & verification)
│   ├── files.py             # File management blueprint (browse/upload/download/remote download)
│   ├── settings.py           # User settings blueprint (avatar/password/2FA management)
│   ├── models.py            # Database models & CRUD operations
│   ├── utils.py             # Utility functions (hashing/JWT/path safety/background download)
│   ├── cli.py               # Command-line tool (reset-2fa)
│   ├── static/              # Static assets (CSS/JS/FontAwesome)
│   └── templates/           # Jinja2 page templates
├── docker-compose.yml       # Docker Compose orchestration file
├── Dockerfile               # Docker image build file
├── requirements.txt         # Python dependencies
└── README.md
```



## ⭐ Star History

If SnowDrive has been helpful, please give it a Star ⭐ to show your support. Every star motivates us to keep improving!

[![Star History Chart](https://api.star-history.com/svg?repos=lclty/snowdrive&type=Date)](https://star-history.com/#lclty/snowdrive&Date)

## 🤝 Contributing

We warmly welcome contributions of any kind, whether code, documentation, or creative ideas:

- 🐛 **Report Bugs**: Submit issues via [GitHub Issues](https://github.com/lclty/snowdrive/issues)
- 🚀 **Submit Code**: Fork the repo → Create a feature branch → Make changes and commit → Open a Pull Request
- 📖 **Improve Documentation**: Fix typos, add explanations, optimize formatting to help newcomers get started faster

> Before submitting a PR, please ensure the code style is consistent with the project and develop on a new branch first.

## 💖 Support the Project

If you find SnowDrive useful, consider:

- Clicking the ⭐ **Star** at the top right of the repository to help more people discover it
- Recommending it to friends who need a personal NAS / private cloud solution

Every star and share is the greatest encouragement to us ❤️



## 📄 License

This project is open-sourced under the MIT License. See the [LICENSE](LICENSE) file for details.
