"""
Gunicorn configuration for E-Eye Photorefractor Operator Web Interface.

Architecture note:
SSE (Server-Sent Events: /api/distance, /api/sessions/<id>/events,
/api/sessions/<id>/record/stream) and MJPEG (/api/preview.mjpg) hold persistent
HTTP connections open. A standard synchronous worker pool (`sync`) would starve
all HTTP handling when 2 or more streaming tabs are open.

Therefore, this configuration uses the `gthread` worker class with multi-threading:
1 worker process x 12 threads = 12 concurrent connection capacity, allowing multiple
active streams alongside instantaneous handling of REST API requests.
"""

import os

bind = os.environ.get("BIND", "0.0.0.0:5000")
workers = 1  # The camera and GPIO must have exactly one process owner.
threads = int(os.environ.get("GUNICORN_THREADS", 12))
worker_class = "gthread"
worker_connections = 1000
timeout = 120
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True
enable_stdio_inheritance = True
