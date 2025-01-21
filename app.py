from flask import Flask, request, send_file, jsonify, render_template
import cv2
import os
import zipfile
import tempfile
import webbrowser
from threading import Timer

app = Flask(__name__, template_folder='templates')

def extract_frames(video_path, output_folder, frames_per_second, video_name):
    os.makedirs(output_folder, exist_ok=True)
    video_capture = cv2.VideoCapture(video_path)
    fps = int(video_capture.get(cv2.CAP_PROP_FPS))
    frame_interval = fps // frames_per_second
    frame_count = 0
    saved_frame_count = 0
    while True:
        ret, frame = video_capture.read()
        if not ret:
            break
        if frame_count % frame_interval == 0:
            output_filename = os.path.join(output_folder, f"{video_name}_{saved_frame_count:04d}.jpg")
            cv2.imwrite(output_filename, frame)
            saved_frame_count += 1
        frame_count += 1
    video_capture.release()
    return saved_frame_count

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_videos():
    if 'videos' not in request.files:
        return jsonify({'error': 'No video files provided'}), 400

    files = request.files.getlist('videos')
    frames_per_second = int(request.form.get('fps', 1))

    # 建立臨時資料夾
    with tempfile.TemporaryDirectory() as temp_dir:
        all_frames_folder = os.path.join(temp_dir, "frames")
        os.makedirs(all_frames_folder, exist_ok=True)

        # 處理每個影片
        for file in files:
            original_filename = file.filename
            video_name, _ = os.path.splitext(original_filename)
            video_path = os.path.join(temp_dir, original_filename)
            file.save(video_path)

            output_subfolder = os.path.join(all_frames_folder, video_name)
            extract_frames(video_path, output_subfolder, frames_per_second, video_name)

        # 壓縮所有圖片
        zip_filename = "all_videos_frames.zip"
        zip_filepath = os.path.join(temp_dir, zip_filename)
        with zipfile.ZipFile(zip_filepath, 'w') as zipf:
            for root, _, files in os.walk(all_frames_folder):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, all_frames_folder)  # 確保壓縮檔內保持相對路徑
                    zipf.write(full_path, arcname)

        return send_file(zip_filepath, as_attachment=True)

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")
if __name__ == '__main__':
    Timer(1, open_browser).start()  # 延遲 1 秒後自動開啟瀏覽器
    app.run(debug=True)
