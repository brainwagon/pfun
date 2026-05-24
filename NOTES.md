# Notes

## Binding to port 80 as a non-root user

Linux restricts ports below 1024 to root. Since the `pfun` systemd service runs as the `pfun` user (not root), gunicorn cannot bind to port 80 by default.

The fix is adding `AmbientCapabilities=CAP_NET_BIND_SERVICE` to `pfun.service` under `[Service]`. This grants the process the specific capability to bind privileged ports without running as root.
