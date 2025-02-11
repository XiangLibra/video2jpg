import os
import sys
import tempfile
import uuid
import threading
import zipfile
import cv2
import webbrowser
from threading import Timer

from flask import Flask, request, jsonify, send_file, render_template


def resource_path(relative_path: str) -> str:
    """
    幫助 Flask 在被 PyInstaller 打包後，仍能正確取得 templates、static 等資源的路徑。
    - 開發時(未打包)  : 直接以當前檔案位置為基準
    - 打包後(sys._MEIPASS): PyInstaller 會將資源解壓到此暫存資料夾
    """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# 若有 static 資料夾，同樣用 resource_path() 來取得路徑
template_dir = resource_path('templates')
static_dir = resource_path('static')

app = Flask(
    __name__,
    template_folder=template_dir,
    static_folder=static_dir
)

# 簡易任務管理結構
tasks = {}
# tasks[job_id] = {
#   "progress": 0~100,
#   "status": "processing"/"done"/"error",
#   "zip_path": "/path/to/zip",
#   "error": ""
# }


def extract_frames_and_zip(video_info_list, output_folder, fps=None, interval=None, job_id=None):
    """
    從多個影片擷取影格並壓縮成單一ZIP (背景執行)。
    video_info_list: [(video_path, video_name), (video_path2, video_name2), ...]
    """

    try:
        os.makedirs(output_folder, exist_ok=True)
        
        # 1) 先計算所有影片的總影格數量，以便整體進度計算
        total_frames_all = 0
        for (video_path, video_name) in video_info_list:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            if total_frames < 1:
                total_frames = 1
            total_frames_all += total_frames

        if total_frames_all == 0:
            total_frames_all = 1
        
        # 2) 依序處理每支影片
        processed_frames_all = 0  # 已處理的影格總數

        for (video_path, video_name) in video_info_list:
            # 為該影片單獨建立資料夾 (同一個 output_folder 底下)
            video_folder = os.path.join(output_folder, video_name)
            os.makedirs(video_folder, exist_ok=True)

            video_capture = cv2.VideoCapture(video_path)
            total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                total_frames = 1  # 避免除以0

            video_fps = int(video_capture.get(cv2.CAP_PROP_FPS))
            if video_fps <= 0:
                video_fps = 30  # 給個預設值

            # 計算取幀間隔
            if fps:
                frame_interval = max(1, video_fps // int(fps))
            elif interval:
                frame_interval = max(1, int(video_fps * float(interval)))
            else:
                frame_interval = 1

            frame_count = 0

            # 擷取影格
            while True:
                ret, frame = video_capture.read()
                if not ret:
                    break

                if frame_count % frame_interval == 0:
                    # 存在該影片的獨立資料夾
                    saved_frame_count = frame_count // frame_interval
                    filename = f"{video_name}_{saved_frame_count:04d}.jpg"
                    cv2.imwrite(os.path.join(video_folder, filename), frame)

                frame_count += 1
                processed_frames_all += 1

                # 每處理一個 frame，更新進度(取前 90% 當作擷取影格階段)
                tasks[job_id]["progress"] = int((processed_frames_all / total_frames_all) * 90)

            video_capture.release()

        # 3) 壓縮檔案 (進度：90% -> 100%)
        zip_filename = "all_videos_frames.zip"
        zip_path = os.path.join(output_folder, zip_filename)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(output_folder):
                for f in files:
                    # 把產生的 JPG 都加進去，但不包含 ZIP 本身
                    if f.endswith(".jpg"):
                        full_path = os.path.join(root, f)
                        arcname = os.path.relpath(full_path, output_folder)
                        zipf.write(full_path, arcname)

        tasks[job_id]["progress"] = 100
        tasks[job_id]["status"] = "done"
        tasks[job_id]["zip_path"] = zip_path

    except Exception as e:
        tasks[job_id]["status"] = "error"
        tasks[job_id]["error"] = str(e)


@app.route("/")
def index():
    """首頁：渲染前端 index.html"""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_videos():
    """接收多個影片、建立背景任務，馬上回應 job_id，前端可輪詢進度。"""
    if "videos" not in request.files:
        return jsonify({"error": "No video files provided"}), 400

    files = request.files.getlist("videos")
    fps = request.form.get("fps")
    interval = request.form.get("interval")

    # 判斷是 fps 或 interval
    if interval:
        interval = float(interval)
    elif fps:
        fps = int(fps)
    else:
        return jsonify({"error": "No valid frame extraction option provided"}), 400

    # 建一個 job_id 來追蹤任務狀態
    job_id = str(uuid.uuid4())
    tasks[job_id] = {
        "progress": 0,
        "status": "processing",
        "zip_path": None,
        "error": ""
    }

    # 建立臨時目錄，存放影格 & ZIP
    temp_dir = tempfile.mkdtemp()

    # 把所有影片先存到臨時資料夾，同時建立一個 list 提供後面使用
    video_info_list = []
    for file in files:
        original_filename = file.filename
        video_name, _ = os.path.splitext(original_filename)
        video_path = os.path.join(temp_dir, original_filename)
        file.save(video_path)
        video_info_list.append((video_path, video_name))

    # 背景執行緒
    def worker():
        extract_frames_and_zip(
            video_info_list=video_info_list,
            output_folder=temp_dir,
            fps=fps,
            interval=interval,
            job_id=job_id
        )

    threading.Thread(target=worker, daemon=True).start()

    # 立即回傳 job_id
    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>", methods=["GET"])
def get_progress(job_id):
    """返回 job 的進度與狀態"""
    if job_id not in tasks:
        return jsonify({"error": "Invalid job_id"}), 404
    return jsonify({
        "progress": tasks[job_id]["progress"],
        "status": tasks[job_id]["status"],
        "error": tasks[job_id]["error"]
    })


@app.route("/download/<job_id>")
def download_zip(job_id):
    """下載產生的 ZIP 檔案"""
    if job_id not in tasks:
        return jsonify({"error": "Invalid job_id"}), 404

    if tasks[job_id]["status"] != "done":
        return jsonify({"error": f"Job {job_id} not finished"}), 400

    zip_path = tasks[job_id]["zip_path"]
    if not zip_path or not os.path.exists(zip_path):
        return jsonify({"error": "ZIP file missing"}), 404

    return send_file(zip_path, as_attachment=True)
# 自動開啟瀏覽器
def open_browser():
    webbrowser.open_new("http://localhost:5002")

if __name__ == "__main__":
    # 若在開發階段，可自行調整 debug, port 等
    # app.run(debug=False, port=5002)
    Timer(2, open_browser).start()
    # app.run(debug=False, port=5002, use_reloader=False)
    app.run(debug=False, port=5002)
