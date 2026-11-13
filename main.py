import glob
import os
import subprocess
from flask import Flask, request, send_file, jsonify, after_this_request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

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
    command = [
        'yt-dlp',
        '-x', '--audio-format', 'mp3', '--audio-quality', '0',
        '-o', f"output_{token}.%(ext)s",
        url,
    ]

    try:
        subprocess.run(
            command, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=600,  # 10 minutes — a hung download can't hang the server forever
        )
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Download timed out after 10 minutes'}), 504
    except subprocess.CalledProcessError as e:
        detail = e.stderr.decode('utf-8', errors='replace').strip()
        return jsonify({'error': detail or 'yt-dlp failed'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
