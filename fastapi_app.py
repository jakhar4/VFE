#!/usr/bin/env python3
"""
Example FastAPI application for extracting video I-frames with FFmpeg,
plus an HTML page to upload a video and download frames.

Install required packages:
  pip install fastapi uvicorn python-multipart pillow

Run:
  uvicorn fastapi_app:app --reload

Open in your browser:
  http://127.0.0.1:8000
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime
from zipfile import ZipFile
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel
from PIL import Image

# 1) Create a directory structure for templates and static files:
#    - templates/
#        index.html
#    - static/
#        (optional for CSS/JS if needed)
#
# 2) Then mount those directories so FastAPI can serve them.

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# For simplicity, we'll store the uploaded video in memory or a temp file,
# then output frames to `output_frames`.
OUTPUT_DIR = "output_frames"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ========== Helper Functions ==========

def ffmpeg_exists() -> bool:
    """
    Check if ffmpeg is available either as a bundled binary (in sys._MEIPASS)
    or on PATH.
    """
    # 1) Check for bundled ffmpeg if running in a frozen app (PyInstaller, etc.).
    if getattr(sys, 'frozen', False):
        bundle_dir = os.path.dirname(sys.executable)
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
        if os.path.exists(ffmpeg_path):
            # Make executable on *nix
            os.chmod(ffmpeg_path, 0o755)
            return True

    # 2) Otherwise, check system ffmpeg.
    try:
        subprocess.run(["ffmpeg", "-version"],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception:
        return False


def extract_iframes(video_file_path: str, output_folder: str):
    """
    Extract I-frames from the given video file path using ffmpeg.
    Output: frame_1.jpg, frame_2.jpg, etc. in `output_folder`.
    """
    # Use system or bundled ffmpeg
    ffmpeg_cmd = "ffmpeg"
    if getattr(sys, 'frozen', False):
        bundle_dir = os.path.dirname(sys.executable)
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
        if os.path.exists(ffmpeg_path):
            ffmpeg_cmd = ffmpeg_path

    os.makedirs(output_folder, exist_ok=True)

    # Clear old frames from output folder (optional).
    # If you only want the latest frames, remove old ones first:
    for f in os.listdir(output_folder):
        if f.endswith(".jpg") or f.endswith(".png"):
            os.remove(os.path.join(output_folder, f))

    command = [
        ffmpeg_cmd, "-i", video_file_path,
        "-vf", "select='eq(pict_type,PICT_TYPE_I)'",
        "-vsync", "vfr",
        os.path.join(output_folder, "frame_%d.jpg")
    ]

    subprocess.run(command, check=True)


# ========== Pydantic Models ==========

class FrameSelection(BaseModel):
    """Used for selecting frames in the request body."""
    filenames: List[str]


# ========== Routes/Endpoints ==========

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """
    Render an HTML page with:
      1) Upload form
      2) "Extract frames" button
      3) Gallery of frames (once extracted)
    """
    return templates.TemplateResponse("index.html", {
        "request": request,
        "frames": _get_frames_list(),
    })


@app.post("/upload-video", response_class=HTMLResponse)
async def upload_video(request: Request, file: UploadFile = File(...)):
    """
    Endpoint to receive a video file upload and extract I-frames.
    """
    if not ffmpeg_exists():
        raise HTTPException(status_code=500, detail="ffmpeg not found on server.")

    # Save the uploaded file to a temporary location
    input_video_path = "temp_video.mp4"
    with open(input_video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Extract the frames
    try:
        extract_iframes(input_video_path, OUTPUT_DIR)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Error extracting frames: {e}")
    finally:
        # Clean up the temporary file
        if os.path.exists(input_video_path):
            os.remove(input_video_path)

    # Return the same HTML but with frames displayed
    return templates.TemplateResponse("index.html", {
        "request": request,
        "frames": _get_frames_list(),
        "message": "Frames extracted successfully!"
    })


@app.get("/frames/{filename}")
def get_frame(filename: str):
    """
    Serve a single frame image from output_frames folder.
    """
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Frame not found.")
    return FileResponse(file_path)


@app.post("/download-zip")
def download_zip(selection: FrameSelection):
    """
    Download selected frames as a single ZIP file.
    """
    selected_files = selection.filenames
    if not selected_files:
        raise HTTPException(status_code=400, detail="No frames selected.")

    # Validate files exist
    real_files = []
    for filename in selected_files:
        file_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(file_path):
            real_files.append(file_path)
    
    if not real_files:
        raise HTTPException(status_code=400, detail="No valid frames found.")

    # Create a zip in memory
    from io import BytesIO
    zip_buffer = BytesIO()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"frames_{timestamp}.zip"

    with ZipFile(zip_buffer, "w") as zipf:
        for file_path in real_files:
            arcname = os.path.basename(file_path)
            zipf.write(file_path, arcname=arcname)

    zip_buffer.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="{zip_filename}"'
    }
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


@app.post("/download-individual")
async def download_individual(selection: FrameSelection):
    """
    Zips and returns individual frames to user in one shot (similar to /download-zip).
    If you truly want to serve them one-by-one, you'd need multiple requests
    or some front-end logic. For simplicity, we reuse a zip approach.
    """
    return download_zip(selection)  # same logic for demo


# ========== Utility ==========

def _get_frames_list() -> List[str]:
    """
    Return list of frame filenames in the output folder.
    """
    if not os.path.exists(OUTPUT_DIR):
        return []
    frames = sorted(f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".jpg"))
    return frames
