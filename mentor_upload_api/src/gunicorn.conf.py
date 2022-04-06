# Gunicorn configuration file
# https://docs.gunicorn.org/en/stable/configure.html#configuration-file
# https://docs.gunicorn.org/en/stable/settings.html

# needs ip set or will be unreachable from host
# regardless of docker-run port mappings
bind = "0.0.0.0:5000"

# workers silent for this many seconds get killed and restarted (default: 30)
timeout=120