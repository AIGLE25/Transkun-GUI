# Transkun-GUI
A simple GUI for Transkun Expresive Piano Transcription tool.

Transkun GUI is a graphical interface for **Transkun** https://github.com/Yujia-Yan/Transkun, a tool that converts audio and video files into MIDI format. This project focuses solely on the **GUI part**, providing an interface for batch conversion and some advanced options.

> **Note:** This repository contains only the GUI frontend. The core conversion logic and dependencies like FFmpeg and the Transkun backend should be installed and configured separately.
<img width="652" height="567" alt="image" src="https://github.com/user-attachments/assets/69c7df76-acc1-429b-9d0f-740c0e605550" />

## Features

- Batch conversion of audio to MIDI  
- Extraction of audio from video files using local FFmpeg  
- File queue management


## Getting Started
To get the gui working you need Transkun (obvious) and FFMPEG.

1. To get Transkun you need python3 (for me, 3.12 is working) and run "pip3 install transkun" in your CLI,

2. To get ffmpeg (release build) go to "https://www.gyan.dev/ffmpeg/builds" once downloaded, check in the bin folder and put ffmpeg's files: "ffmpeg.exe", "ffplay.exe", "ffprobe.exe" in the root directory of this folder (Transkun GUI folder)

3. Done.

## How to build and install standalone version (Python needed)

Put the TranskunGUIstandalone.py in a folder, Download the .spec file and put it in the same folder then run it with this command "pyinstaller Transkun GUI.spec" and check the result in the dist folder.

You will have to download the transkun folder, and put it in _internal folder, and download the pretrained folder in the Transkun original repo (to get the .pt model because gihub don't let me upload this file): https://github.com/Yujia-Yan/Transkun/tree/main/transkun/pretrained, and put the pretrained folder in _internal folder too.

