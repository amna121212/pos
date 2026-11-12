# Deployment

The site at <https://amna.areeenaa.com> is served by Nginx over TLS and proxied to
Gunicorn on `127.0.0.1:8001`, running as the unprivileged `posapp` user. ParkSphere
(`rameen.areeenaa.com`, port 8002, `parksphere_db`) is a separate server block and a
separate process; nothing below touches it.

## Layout on the server

| Path | Purpose |
| --- | --- |
| `/opt/student-projects/pos` | Application source, revision and venv (`posapp:posapp`, `0750`) |
| `/opt/student-projects/pos/.venv` | Virtual environment |
| `/opt/student-projects/pos/instance` | Optional local overrides, `0700` |
| `/etc/pos/pos.env` | Credentials and session key (`root:posapp`, `0640`) |
| `/etc/systemd/system/pos.service` | Gunicorn unit |
| `/var/log/pos/access.log`, `error.log` | Gunicorn logs (`posapp:posapp`, `0750`) |
| `/etc/nginx/sites-available/amna.areeenaa.com` | Nginx server block |
| `/etc/letsencrypt/live/amna.areeenaa.com/` | Certificate managed by Certbot |
| `/root/db-backups/` | Database dumps |

`/opt/student-projects` is mode `0711`: traversable, not listable. Each project
directory keeps its own `0750` ownership, so ParkSphere stays private.

## Unit file

```ini
[Unit]
Description=Amna POS Flask application
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=posapp
Group=posapp
WorkingDirectory=/opt/student-projects/pos
EnvironmentFile=/etc/pos/pos.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/student-projects/pos/.venv/bin/gunicorn \
    --workers 3 \
    --threads 2 \
    --timeout 60 \
    --graceful-timeout 20 \
    --bind 127.0.0.1:8001 \
    --access-logfile /var/log/pos/access.log \
    --error-logfile /var/log/pos/error.log \
    --capture-output \
    wsgi:app
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/student-projects/pos /var/log/pos

[Install]
WantedBy=multi-user.target
```

`wsgi.py` builds the app with `create_app()`, so the same factory is used by the
tests, the CLI and the server.

## Nginx block

```nginx
server {
    server_name amna.areeenaa.com;

    client_max_body_size 4m;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
        proxy_redirect off;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/amna.areeenaa.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/amna.areeenaa.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if ($host = amna.areeenaa.com) {
        return 301 https://$host$request_uri;
    }
    listen 80;
    server_name amna.areeenaa.com;
    return 404;
}
```

`X-Forwarded-Proto` matters: the app trusts exactly one proxy hop (`ProxyFix`), so
`url_for(_external=True)` and the secure session cookie are correct behind TLS.

## Release procedure

```bash
cd /opt/student-projects/pos
.venv/bin/pip install -r requirements.txt       # only when requirements change
.venv/bin/python -m pytest -q                   # gate the release on green tests
.venv/bin/flask --app wsgi db current           # confirm the revision you expect
sudo systemctl restart pos.service
systemctl is-active pos.service
curl -s -o /dev/null -w '%{http_code}\n' https://amna.areeenaa.com/login
```

Always confirm you are connected to `retail_pos_db` before running a migration:

```bash
grep POS_DB_NAME /etc/pos/pos.env
```

## Rollback

The application is code plus a database revision, so roll back in that order:

1. **Code** — restore the previous source tree, then
   `sudo systemctl restart pos.service`. Keep a copy of the tree you are replacing.
2. **Nginx** — the previous block was saved as
   `/root/nginx-amna-<UTC stamp>.bak`:
   ```bash
   sudo cp /root/nginx-amna-20261112T070945Z.bak /etc/nginx/sites-available/amna.areeenaa.com
   sudo nginx -t && sudo systemctl reload nginx
   ```
3. **Database** — restore the dump taken before the change into a scratch database,
   verify it, and only then decide whether to swap. See `docs/DATABASE.md`.
   Do not `flask db downgrade` a database that already holds recorded sales.

## Logs

```bash
sudo tail -f /var/log/pos/error.log        # Gunicorn errors and tracebacks
sudo tail -f /var/log/pos/access.log       # requests
sudo journalctl -u pos.service -n 100      # unit lifecycle and restart reason
sudo tail -f /var/log/nginx/error.log      # proxy errors, 502s
```

The app logs an exception with a traceback for an unhandled 500 and rolls the
session back, so a failed checkout never half-writes an order.

## HTTPS verification

```bash
curl -sI https://amna.areeenaa.com/login | head -3          # 200, text/html
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://amna.areeenaa.com/
                                                            # 301 to https
curl -s -o /dev/null -w '%{http_code}\n' https://amna.areeenaa.com/static/css/app.css
                                                            # 200 text/css
openssl s_client -connect amna.areeenaa.com:443 -servername amna.areeenaa.com </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -issuer
```

Certificate renewal is Certbot's systemd timer; the server block keeps the
Certbot-managed lines intact.

## Environment file

```bash
sudo install -o root -g posapp -m 0640 /dev/null /etc/pos/pos.env
sudo editor /etc/pos/pos.env
```

Contents, names only:

```
POS_DB_USER=pos_app
POS_DB_PASSWORD=...
POS_DB_HOST=127.0.0.1
POS_DB_PORT=5432
POS_DB_NAME=retail_pos_db
POS_SECRET_KEY=...            # 64 hex characters, rotate to invalidate all sessions
POS_SESSION_COOKIE_SECURE=1
POS_SIGNUP_ENABLED=1          # 0 closes public registration
```

Never commit this file. `config/pos.env.example` is the secret-free template.

## Security posture

- PostgreSQL listens on `127.0.0.1:5432` only; the app connects with `pos_app`, not
  a superuser.
- Gunicorn binds `127.0.0.1:8001` only; the port is not exposed.
- The service runs as `posapp` with `NoNewPrivileges`, `PrivateTmp`,
  `ProtectSystem=full` and `ProtectHome`.
- Session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` behind TLS.
- Every state change requires a CSRF token; every page re-checks role and tenant.
