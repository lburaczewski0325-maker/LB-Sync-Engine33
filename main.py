import glob
import os
import subprocess
import tempfile
from flask import Flask, request, send_file, jsonify, after_this_request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# YouTube cookies (optional), MULTIPLE SETS with fallback (Lenny, Nov 13
# ~00:57 AM): YTDLP_COOKIES = set 1, YTDLP_COOKIES_2.._5 = sets 2-5.
# Each holds the full Netscape cookies.txt content of a DIFFERENT signed-in
# Google account's YouTube session. /convert tries them in order; when one
# set gets zapped (expired, revoked, flagged) the next set takes over, so
# one dead session can't kill the converter. They are NEVER committed to
# the repo (public) — env vars only. Each set is written once to a temp
# file and passed to yt-dlp as --cookies, which makes YouTube see a
# logged-in user instead of a datacenter IP.
_COOKIE_PATHS = None


def _cookie_files():
    global _COOKIE_PATHS
    if _COOKIE_PATHS is not None:
        return _COOKIE_PATHS
    names = ['YTDLP_COOKIES'] + ['YTDLP_COOKIES_%d' % i for i in range(2, 6)]
    paths = []
    for name in names:
        content = os.environ.get(name)
        if not content:
            continue
        fd, path = tempfile.mkstemp(prefix='yt-cookies-', suffix='.txt')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        paths.append(path)
    _COOKIE_PATHS = paths
    return paths

# LB-Sync-Engine33 — backend: video URL -> MP3 download


@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'LB-Sync-Engine33'})


@app.route('/convert', methods=['POST'])
def convert_video():
    data = request.get_json(silent=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    token = os.urandom(4).hex()
    output_filename = f"output_{token}.mp3"

    # yt-dlp command to extract audio and encode to high quality MP3 (handles playlists too)
    # Android player client (from the Nov 13 ~00:32 AM fix): it works locally
    # and stays as the client choice — but it does NOT dodge the datacenter-IP
    # block on Render (proven ~00:49 AM: skip=webpage doesn't skip the webpage
    # fetch, so the web AND android clients both get 429/403 there). Cookies
    # are the real path. Scoped to youtube only.
    base_command = [
        'yt-dlp',
        '-x', '--audio-format', 'mp3', '--audio-quality', '0',
        '--extractor-args', 'youtube:player_client=android;skip=webpage',
        '-o', f"output_{token}.%(ext)s",
        url,
    ]

    # Try each cookie set in order, then once with no cookies at all (that
    # last attempt keeps direct media links working even if every set is
    # dead). A set that fails — zapped session, 429/403, bad file — falls
    # through to the next; only the last failure is reported. Success means
    # yt-dlp exited 0, so a partial file from a failed attempt is cleaned
    # up below instead of being sent.
    attempts = _cookie_files() + [None]
    last_error = None
    converted = False
    for cookies in attempts:
        command = ['yt-dlp']
        if cookies:
            command += ['--cookies', cookies]
        command += base_command[1:]
        try:
            subprocess.run(
                command, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=600,  # 10 minutes per attempt — a hung download can't hang the server forever
            )
            converted = True
            break
        except subprocess.TimeoutExpired:
            last_error = 'Download timed out after 10 minutes'
        except subprocess.CalledProcessError as e:
            last_error = e.stderr.decode('utf-8', errors='replace').strip() or 'yt-dlp failed'
        except Exception as e:
            last_error = str(e)
    if not converted:
        for f in glob.glob(f"output_{token}*.mp3"):
            try:
                os.remove(f)
            except OSError:
                pass
        return jsonify({'error': last_error or 'yt-dlp failed'}), 500

    # yt-dlp names the file output_<token>.mp3; for playlists it may append
    # titles, so match by the unique token instead of the generic "output" prefix
    # (the old prefix could grab another request's file when two people convert at once).
    matches = sorted(glob.glob(f"output_{token}*.mp3"))
    if matches:
        output_filename = matches[0]
    if not os.path.exists(output_filename):
        return jsonify({'error': 'Conversion finished but no MP3 file was produced'}), 500

    # Delete the file AFTER the download is sent, not in a finally block —
    # the old finally deleted it before the server had finished streaming it.
    @after_this_request
    def _cleanup(response):
        for f in glob.glob(f"output_{token}*.mp3"):
            try:
                os.remove(f)
            except OSError:
                pass
        return response

    return send_file(output_filename, as_attachment=True, mimetype='audio/mpeg')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
