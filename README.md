# Charity Transparency Web App (Flask + SQLAlchemy)

## Local development

1. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
2. Run the app
   ```bash
   python run.py
   ```

Admin login (by default for local dev):
- Username: `admin`
- Password: `admin123`

## Deploy on Render (recommended settings)

Render needs a Gunicorn start command and environment variables.

### 1) Create a Web Service
In the Render Dashboard:
1. Connect your git repo
2. Choose **Web Service**

### 2) Build Command
Set:
```bash
pip install -r requirements.txt
```

### 3) Start Command
Set:
```bash
gunicorn wsgi:app --workers 2 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT
```

### 4) Environment Variables
At minimum, set:
- `SECRET_KEY` (required for production sessions)

Recommended (optional but practical):
- `ADMIN_USERNAME` (default: `admin`)
- `ADMIN_PASSWORD` (default: `admin123`)
- `DATABASE_URL` (recommended: Render Postgres URL)

If you do NOT want dummy data seeded on every deploy:
- `SEED_DUMMY_DATA=0`

### 5) Uploads
This app stores uploaded post images under `app/static/uploads/`.
On Render, this works for small/typical usage, but note that uploads are tied to the instance’s filesystem.

## Health check / troubleshooting
- Ensure your service can bind to `$PORT` (the start command above does this).
- Check Render build logs for missing dependencies.
- Check Render runtime logs for SQLAlchemy / database connection errors.

