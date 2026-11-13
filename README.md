# LB-Sync-Engine33

Video URL to MP3 conversion backend. Flask + yt-dlp + ffmpeg, served with gunicorn.

## Endpoints

- `GET /` — health check, returns `{"status": "ok", "service": "LB-Sync-Engine33"}`
- `POST /convert` — JSON body `{"url": "<video url>"}` returns the converted MP3 as a download

## Run locally

```bash
pip install -r requirements.txt
python main.py
```

## Deploy (Render)

- Web Service, Python runtime, connect this repo
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn main:app --bind 0.0.0.0:$PORT`
- ffmpeg is preinstalled on Render's native runtimes
- Free tier sleeps after 15 min idle; first request after idle takes ~30–60s to wake up
