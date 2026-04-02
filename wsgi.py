from app import create_app

# Gunicorn entrypoint. Render will call this WSGI callable.
app = create_app()

