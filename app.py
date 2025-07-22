from flask import Flask, request, jsonify
import os
import cv2
import numpy as np
import yt_dlp
import subprocess
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import tempfile
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# === Fonction de téléchargement TikTok ===
def telecharger_tiktok(url):
    output_path = os.path.join(UPLOAD_FOLDER, 'video_tiktok.%(ext)s')
    options = {
        'outtmpl': output_path,
        'format': 'mp4',
        'quiet': True
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])
    return output_path.replace('%(ext)s', 'mp4')

# === Filtre Embellir ===
def embellir(frame):
    frame = cv2.bilateralFilter(frame, 9, 75, 75)
    frame = cv2.convertScaleAbs(frame, alpha=1.15, beta=15)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    s = cv2.add(s, 10)
    hsv = cv2.merge([h, s, v])
    frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
    frame = cv2.filter2D(frame, -1, kernel)
    return frame

# === Compression vidéo ===
def compresser_video(input_path, output_path="video_compressee.mp4", crf=26):
    cmd = [
        "ffmpeg", "-i", input_path, "-vcodec", "libx264", "-crf", str(crf),
        "-preset", "slow", "-acodec", "aac", "-b:a", "128k",
        "-movflags", "+faststart", output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path

# === API principale ===
@app.route("/process", methods=["POST"])
def process():
    source = request.form.get("source")  # tiktok ou pc
    image_time = request.form.get("image_start")
    image_duration = request.form.get("image_duration")
    compresser = request.form.get("compress") == "true"

    image_start = float(image_time) if image_time else None
    image_duration = float(image_duration) if image_duration else None

    video_path = None
    image_path = None

    # === Source vidéo ===
    if source == "tiktok":
        tiktok_url = request.form.get("url")
        if not tiktok_url:
            return jsonify({"error": "Lien TikTok manquant"}), 400
        video_path = telecharger_tiktok(tiktok_url)

    elif source == "pc":
        if "video" not in request.files:
            return jsonify({"error": "Fichier vidéo manquant"}), 400
        file = request.files['video']
        filename = secure_filename(file.filename)
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(video_path)
    else:
        return jsonify({"error": "Source invalide"}), 400

    # === Traitement vidéo ===
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    temp_no_audio = os.path.join(app.config['UPLOAD_FOLDER'], "embellie_no_audio.mp4")
    out = cv2.VideoWriter(temp_no_audio, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(embellir(frame))

    cap.release()
    out.release()

    # === Image à superposer ? ===
    if "image" in request.files:
        file = request.files['image']
        filename = secure_filename(file.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(image_path)

    video_clip = VideoFileClip(temp_no_audio)
    original_audio = VideoFileClip(video_path).audio

    if image_path and image_start is not None and image_duration is not None:
        image_clip = ImageClip(image_path).resize((video_clip.w, video_clip.h))
        image_clip = image_clip.set_duration(image_duration).set_start(image_start).set_position("center")
        final_clip = CompositeVideoClip([video_clip, image_clip])
    else:
        final_clip = video_clip

    final_clip = final_clip.set_audio(original_audio)

    output_path = os.path.join(app.config['UPLOAD_FOLDER'], "video_finale_embellie.mp4")
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", verbose=False, logger=None)

    if compresser:
        compressed_path = os.path.join(app.config['UPLOAD_FOLDER'], "video_compressee.mp4")
        compresser_video(output_path, compressed_path)
        return jsonify({"status": "ok", "video_url": compressed_path})

    return jsonify({"status": "ok", "video_url": output_path})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
