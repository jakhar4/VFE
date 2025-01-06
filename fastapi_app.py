#!/usr/bin/env python3
"""
Example FastAPI application for extracting video I-frames with FFmpeg,
plus an HTML page to upload a video and download frames.
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

app = FastAPI()

# Mount static directory if you have one
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

OUTPUT_DIR = "output_frames"
os.makedirs(OUTPUT_DIR, exist_ok=True)

frames_cache = {}  # In-memory cache for frames

def ffmpeg_exists() -> bool:
    if getattr(sys, 'frozen', False):
        bundle_dir = os.path.dirname(sys.executable)
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
        if os.path.exists(ffmpeg_path):
            os.chmod(ffmpeg_path, 0o755)
            return True

    try:
        subprocess.run(["ffmpeg", "-version"],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except:
        return False

def extract_iframes(video_file_path: str, output_folder: str):
    ffmpeg_cmd = "ffmpeg"
    if getattr(sys, 'frozen', False):
        bundle_dir = os.path.dirname(sys.executable)
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
        if os.path.exists(ffmpeg_path):
            ffmpeg_cmd = ffmpeg_path

    os.makedirs(output_folder, exist_ok=True)

    # Clear old frames (optional)
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

class FrameSelection(BaseModel):
    filenames: List[str]

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "frames": _get_frames_list(),
    })

@app.post("/upload-video", response_class=HTMLResponse)
async def upload_video(request: Request, file: UploadFile = File(...)):
    if not ffmpeg_exists():
        raise HTTPException(status_code=500, detail="ffmpeg not found on server.")

    input_video_path = "temp_video.mp4"
    with open(input_video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        extract_iframes(input_video_path, OUTPUT_DIR)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Error extracting frames: {e}")
    finally:
        if os.path.exists(input_video_path):
            os.remove(input_video_path)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "frames": _get_frames_list(),
        "message": "Frames extracted successfully!"
    })

@app.get("/frames/{filename}")
def get_frame(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Frame not found.")
    return FileResponse(file_path)

@app.post("/download-zip")
async def download_zip(selection: FrameSelection):
    selected_files = selection.filenames
    if not selected_files:
        raise HTTPException(status_code=400, detail="No frames selected.")

    real_files = []
    for filename in selected_files:
        file_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(file_path):
            real_files.append(file_path)

    if not real_files:
        raise HTTPException(status_code=400, detail="No valid frames found.")

    from io import BytesIO
    zip_buffer = BytesIO()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"frames_{timestamp}.zip"

    with ZipFile(zip_buffer, "w") as zipf:
        for file_path in real_files:
            arcname = os.path.basename(file_path)
            zipf.write(file_path, arcname=arcname)

    zip_buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)

@app.post("/download-individual")
async def download_individual(selection: FrameSelection):
    # For this demo, just re-use the ZIP logic:
    return download_zip(selection)

def _get_frames_list() -> List[str]:
    if not os.path.exists(OUTPUT_DIR):
        return []
    return sorted(f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".jpg"))
