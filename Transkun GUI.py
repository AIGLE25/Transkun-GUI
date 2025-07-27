import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import subprocess
import os
import json
import tempfile
import shutil
import mimetypes
import re
import warnings

OPTIONS_FILE = "options.json"

default_options = {
    "use_eval": True,
    "use_weights_only": True,
    "use_reentrant": False,
    "requires_grad": True,
    "device": "cuda"  
}

def load_options():
    if os.path.exists(OPTIONS_FILE):
        try:
            with open(OPTIONS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default_options.copy()

def save_options(opts):
    with open(OPTIONS_FILE, "w") as f:
        json.dump(opts, f, indent=4)

class TranskunGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Transkun GUI")

        self.options = load_options()

        self.file_queue = []
        self.stop_requested = False
        self.drag_start_index = None
        #~~~~~~~~~~~~~~~~~~
        self.conversion_started = False
        self.currently_processing_entry = None
        self.double_click_blocked = False
        self.skip_requested = False
        #~~~~~~~~~~~~~~~~~~

        self.current_processing_progress = 0

        # File list frame + buttons
        frame_list = tk.Frame(root)
        frame_list.pack(padx=10, pady=5, fill="x")

        tk.Label(frame_list, text="File List (order) :").pack(anchor="w")

        self.listbox = tk.Listbox(frame_list, height=8, activestyle="none")
        self.listbox.bind("<Button-1>", self.on_drag_start)
        self.listbox.bind("<B1-Motion>", self.on_drag_motion)
        self.listbox.bind("<ButtonRelease-1>", self.on_drag_release)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-1>", self.on_file_double_click)


        scrollbar = tk.Scrollbar(frame_list, command=self.listbox.yview)
        scrollbar.pack(side="left", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        frame_buttons = tk.Frame(frame_list)
        frame_buttons.pack(side="left", padx=5)

        tk.Button(frame_buttons, text="Add file", command=self.add_files).pack(fill="x", pady=2)
        tk.Button(frame_buttons, text="Delete selected", command=self.remove_selected).pack(fill="x", pady=2)
        tk.Button(frame_buttons, text="Delete all files", command=self.clear_list).pack(fill="x", pady=2)
        tk.Button(frame_buttons, text="Skip", command=self.skip_current_file).pack(fill="x", pady=2)

        # Advanced Options Button
        tk.Button(frame_buttons, text="Advanced options", command=self.open_advanced_options).pack(fill="x", pady=10)

        # Progression
        frame_progress = tk.Frame(root)
        frame_progress.pack(padx=10, pady=5, fill="x")

        tk.Label(frame_progress, text="").pack(anchor="w")
        self.progress_file = ttk.Progressbar(frame_progress, mode="indeterminate")
        self.progress_file.pack(fill="x", pady=2)

        tk.Label(frame_progress, text="Total progress :").pack(anchor="w")

        self.progress_total = ttk.Progressbar(frame_progress, mode="determinate")

        self.progress_canvas = tk.Canvas(frame_progress, height=20, bg="white", highlightthickness=1, highlightbackground="gray")
        self.progress_canvas.pack(fill="x", pady=2)

        self.current_progress_idx = -1 #2552525552525252

        self.progress_canvas.bind("<Configure>", lambda e: self.update_segmented_bar(), len(self.file_queue))

        self.progress_label = tk.Label(frame_progress, text="0/0")
        self.progress_label.pack(anchor="e", padx=5)

        # Console logs
        console_frame = tk.Frame(root)
        console_frame.pack(padx=10, pady=5, fill="both", expand=True)

        # Widget Text (console)
        self.text_console = tk.Text(console_frame, height=10, bg="white", fg="black", state=tk.DISABLED, wrap="word")
        self.text_console.pack(side=tk.LEFT, fill="both", expand=True)

        # Scrollbar
        scrollbar = tk.Scrollbar(console_frame, command=self.text_console.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        self.text_console.config(yscrollcommand=scrollbar.set)

        # To maintain compatibility with self.log_widget
        self.log_widget = self.text_console


        # start/stop
        frame_controls = tk.Frame(root)
        frame_controls.pack(pady=10)

        self.btn_start = tk.Button(frame_controls, text="Start", command=self.start_conversion, bg="green", fg="white", width=20)
        self.btn_start.pack(side="left", padx=5)

        self.btn_stop = tk.Button(frame_controls, text="Stop", command=self.stop_conversion, bg="red", fg="white", width=20, state=tk.DISABLED)
        self.btn_stop.pack(side="left", padx=5)

        # display options at start
        self.log_options()

    def skip_current_file(self):
        self.skip_requested = True

    def on_file_double_click(self, event):
        if self.double_click_blocked:
            return  # Ignore false double clicks that are too close together (not very good fix but better than nothing)

        self.double_click_blocked = True
        self.root.after(300, lambda: setattr(self, 'double_click_blocked', False))  

        widget = event.widget
        index = widget.nearest(event.y)

        if index < 0 or index >= len(self.file_queue):
            return

        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)

        file_entry = self.file_queue[index]

        if file_entry['status'] == 'processing':
            self.log("⚠️ This file is being processed.")
            return

        previous_status = file_entry['status']
        if previous_status == 'done':
            file_entry['status'] = 'pending'
            self.log(f"🔄 {os.path.basename(file_entry['path'])} will be reprocessed.")
        elif previous_status == 'pending':
            file_entry['status'] = 'ignored'
            self.log(f"🚫 {os.path.basename(file_entry['path'])} will be ignored.")
        elif previous_status == 'ignored':
            file_entry['status'] = 'pending'
            self.log(f"✅ {os.path.basename(file_entry['path'])} will be reprocessed.")
        elif previous_status == 'skipped':
            file_entry['status'] = 'pending'
            self.log(f"✅ {os.path.basename(file_entry['path'])} will be reprocessed.")

        self.update_listbox_colors()
        self.update_segmented_bar()
        if previous_status == 'done' or file_entry['status'] == 'done':
            self.refresh_progress_ui()



    def refresh_progress_ui(self):
        total = len(self.file_queue)
        self.current_progress_idx = sum(1 for f in self.file_queue if f["status"] == "done")
        self.update_segmented_bar()
        self.progress_label.config(text=f"{self.current_progress_idx}/{total}")
        self.progress_total["maximum"] = total

    def update_segmented_bar_live_progress(self, target_ratio):
        if not hasattr(self, "_last_progress_ratio"):
            self._last_progress_ratio = 0.0

        steps = 100
        step_delay = 2  
        delta = (target_ratio - self._last_progress_ratio) / steps

        def animate_step(step=0):
            if step >= steps:
                self._last_progress_ratio = target_ratio
                return

            self._last_progress_ratio += delta
            ratio = self._last_progress_ratio

            self.progress_canvas.delete("all")
            total = len(self.file_queue)
            width = self.progress_canvas.winfo_width()
            segment_width = width / total if total > 0 else 0

            for i, entry in enumerate(self.file_queue):
                x0 = i * segment_width
                x1 = (i + 1) * segment_width

                if entry == self.currently_processing_entry:
                    fill_width = x0 + segment_width * ratio
                    self.progress_canvas.create_rectangle(x0, 0, fill_width, 20, fill="orange", outline="black")
                    if fill_width < x1:
                        self.progress_canvas.create_rectangle(fill_width, 0, x1, 20, fill="lightgray", outline="black")
                else:
                    status = entry.get("status", "pending")
                    if status == "done":
                        color = "green"
                    elif status == "ignored":
                        color = "gray"
                    elif status == "skipped":
                        color = "red"
                    else:
                        color = "lightgray"
                    self.progress_canvas.create_rectangle(x0, 0, x1, 20, fill=color, outline="black")

            self.root.after(step_delay, lambda: animate_step(step + 1))

        animate_step()


    def update_segmented_bar(self):
        self.progress_canvas.delete("all")
        file_list = self.file_queue
        total = len(file_list)

        if total == 0:
            return

        width = self.progress_canvas.winfo_width()
        segment_width = width / total

        current_entry = self.currently_processing_entry
        current_idx = file_list.index(current_entry) if current_entry in file_list else -1

        for i, entry in enumerate(file_list):
            x0 = i * segment_width
            x1 = (i + 1) * segment_width

            status = entry.get("status", "pending")

            if status == "skipped":
                color = "red"
            elif status == "done":
                color = "green"
            elif status == "ignored":
                color = "gray"
            elif i == current_idx and status == "processing":
                color = "orange"
            else:
                color = "lightgray"

            self.progress_canvas.create_rectangle(x0, 0, x1, 20, fill=color, outline="black")




    def update_listbox_colors(self, current_index=0):
        for i, file_entry in enumerate(self.file_queue):
            status = file_entry['status']

            if status == 'done':
                color = 'green'    # already converted
            elif status == 'processing' and self.conversion_started:
                color = 'orange'   # on-going
            elif status == 'ignored': 
                color = 'gray'     # ingnored file
            elif status == 'skipped':
                color = 'red'      # skipped due to error/missing     
            else:
                color = 'black'    # waiting
        

            self.listbox.itemconfig(i, {'fg': color})



    def can_move_file(self, index):
        if index < 0 or index >= len(self.file_queue):
            return False
        return self.file_queue[index]["status"] in ("pending", "ignored", "skipped")

    def on_drag_start(self, event):
        idx = self.listbox.nearest(event.y)
        if not self.can_move_file(idx):
            self.drag_start_index = None
            self.drag_current_index = None
            return

        self.drag_start_index = idx
        self.drag_current_index = idx

    def on_drag_motion(self, event):
        if self.drag_start_index is None:
            return

        target_idx = self.listbox.nearest(event.y)
        if not self.can_move_file(target_idx):
            # Do not allow moving to a non-movable file
            target_idx = self.drag_current_index

        if target_idx != self.drag_current_index:
            self.drag_current_index = target_idx
            self.listbox.selection_clear(0, 'end')
            self.listbox.selection_set(self.drag_start_index)
            self.listbox.activate(self.drag_start_index)

    def on_drag_release(self, event):
        if self.drag_start_index is None:
            return

        target_idx = self.listbox.nearest(event.y)
        if not self.can_move_file(target_idx):
            target_idx = self.drag_start_index

        if target_idx != self.drag_start_index:
            # Only swap "pending" files
            self.file_queue[self.drag_start_index], self.file_queue[target_idx] = \
                self.file_queue[target_idx], self.file_queue[self.drag_start_index]
            self.update_listbox()

        self.drag_start_index = None
        self.drag_current_index = None
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(target_idx)
        self.listbox.activate(target_idx)


    def update_listbox(self):
        self.listbox.delete(0, tk.END)
        for idx, file_entry in enumerate(self.file_queue, 1):
            self.listbox.insert(tk.END, f"{idx}. {os.path.basename(file_entry['path'])}")
        self.update_listbox_colors()


    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Add file",
            filetypes=[("All Files", "*.*")]
        )

        added_any = False
        for f in files:
            # Avoid adding a file already present in the queue
            if not any(entry['path'] == f for entry in self.file_queue):
                self.file_queue.append({'path': f, 'status': 'pending'})
                added_any = True

        if added_any:
            self.update_listbox()
            self.root.after(0, self.update_progress_on_add)  



    def update_progress_on_add(self):
        if not self.conversion_started:
            total = len(self.file_queue)
            done_count = sum(1 for f in self.file_queue if f["status"] == "done")
            self.update_segmented_bar()
            self.progress_label.config(text=f"{done_count}/{total}")
            self.progress_total["maximum"] = total
        else:
            # "If conversion is in progress, just update the bar without resetting
            self.update_segmented_bar()
            self.progress_total["maximum"] = len(self.file_queue)
            self.progress_label.config(text=f"{self.current_progress_idx}/{len(self.file_queue)}")


    def remove_selected(self):
        selected = list(self.listbox.curselection())
        removed = False

        for index in reversed(selected):
            file_entry = self.file_queue[index]

            if file_entry["status"] == "processing":
                # self.log(f"⚠️ File deleted during processing : {file_entry['path']}")
                # Remove it from the queue — the main loop will detect this and move to the next one
                del self.file_queue[index]
                removed = True
            else:
                del self.file_queue[index]
                removed = True

        if removed:
            self.update_listbox()
            self.update_progress_after_change()

            
    def update_progress_after_change(self):
        total = len(self.file_queue)
        done_count = sum(1 for f in self.file_queue if f["status"] == "done")
        self.current_progress_idx = done_count
        self.update_segmented_bar()
        self.progress_total["maximum"] = total
        self.progress_label.config(text=f"{done_count}/{total}")

    def clear_list(self):
        self.file_queue.clear()
        self.update_listbox()
        self.update_progress_after_change()

    def log(self, text):
        self.text_console.config(state=tk.NORMAL)
        self.text_console.insert(tk.END, text + "\n")
        self.text_console.see(tk.END)
        self.text_console.config(state=tk.DISABLED)

    def log_replace_last(self, new_line):
        """replace last ligne of widget log (for progress bar)."""
        self.log_widget.config(state="normal")
        self.log_widget.delete("end-2l", "end-1l")  
        self.log_widget.insert("end", new_line + "\n")
        self.log_widget.see("end")
        self.log_widget.config(state="disabled")

    def log_options(self):
        self.log("⚙️ Current options :")
        self.log(f" - model.eval() : {'✔' if self.options.get('use_eval', True) else '✘'}")
        self.log(f" - weights_only=True : {'✔' if self.options.get('use_weights_only', True) else '✘'}")
        self.log(f" - use_reentrant=True : {'✔' if self.options.get('use_reentrant', True) else '✘'}")
        self.log(f" - requires_grad=True : {'✔' if self.options.get('requires_grad', True) else '✘'}")
        self.log(f" - device : {self.options.get('device', 'cuda')}")
    def get_unique_output_path(self, base_path):

        if not os.path.exists(base_path):
            return base_path

        base, ext = os.path.splitext(base_path)
        counter = 1
        while True:
            new_path = f"{base} ({counter}){ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1
    def refresh_progress_bar(self):
        total = len(self.file_queue)
        # Count the files already finished to keep track of progress
        done_count = sum(1 for f in self.file_queue if f["status"] == "done")

        # Updates the segmented bar and the label with the current progress
        self.update_segmented_bar()
        self.progress_label.config(text=f"{done_count}/{total}")
        self.progress_total["maximum"] = total


    def start_conversion(self):
        if not self.file_queue:
            messagebox.showwarning("No file", "add file to convert.")
            return
        for entry in self.file_queue:
            if entry["status"] == "skipped":
                entry["status"] = "pending"
        self.stop_requested = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        self.current_progress_idx = 0
        self.update_listbox_colors(0)
        self.update_segmented_bar()


        threading.Thread(target=self.convert_all_files, daemon=True).start()

    def stop_conversion(self):
        if messagebox.askyesno("STOP", "Confirm ?"):
            self.stop_requested = True
            self.btn_stop.config(state=tk.DISABLED)
            # self.log("⏳ Stop task")

            # Immediate interruption if a process is running
            if hasattr(self, "current_process") and self.current_process and self.current_process.poll() is None:
                try:
                    # self.log("⛔ Interruption of the current file...")
                    self.current_process.terminate()
                except Exception as e:
                    self.log(f"⚠️ Unable to interrupt the process : {e}")

    def run_transkun_and_capture_progress(self, cmd):
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            self.current_process = process
            last_progress_line = None
            skipping_warning_block = False

            for raw_line in process.stdout:
                line = raw_line.rstrip()

                if not line.strip():
                    continue

                if self.stop_requested:
                    process.terminate()
                    process.wait()
                    return -1

                if self.skip_requested:
                    self.skip_requested = False
                    if self.currently_processing_entry:
                        self.currently_processing_entry["status"] = "ignored"
                        self.log(f"⏭ Skipped by user: {os.path.basename(self.currently_processing_entry['path'])}")
                        self.update_listbox()
                        self.update_segmented_bar()
                    process.terminate()
                    process.wait()
                    return -3


                if self.currently_processing_entry is not None:
                    path = self.currently_processing_entry.get('path')
                    if not path or not os.path.exists(path):
                        self.log(f"⛔ skipping Missing file {os.path.basename(path) if path else '(unknown)'}")
                        process.terminate()
                        process.wait()
                        return -2
                if self.currently_processing_entry not in self.file_queue:
                    self.log("⚠️ File removed from the list during conversion, moving on to the next one.")
                    process.terminate()
                    process.wait()
                    return -3

                if line.startswith("[Transkun] Progression:"):
                    percent_pos = line.find('%')
                    if percent_pos != -1:
                        line = line[:percent_pos + 1]

                    if line != last_progress_line:
                        if last_progress_line is None:
                            self.log(line)
                        else:
                            self.log_replace_last(line)
                        last_progress_line = line

                    # extract % from logs
                    match = re.search(r'(\d{1,3})%', line)
                    if match:
                        percent = int(match.group(1))
                        ratio = min(percent / 100, 1.0)
                        self.update_segmented_bar_live_progress(ratio)
                        self.root.update_idletasks()

                    skipping_warning_block = False
                    continue

                if (
                    "UserWarning" in line or
                    "torch.load" in line or
                    "eval_frame" in line or
                    "return fn(" in line or
                    "checkpoint =" in line or
                    "warnings.warn" in line
                ):
                    skipping_warning_block = True
                    continue

                if skipping_warning_block:
                    if line.startswith("  ") or line.strip().endswith(")") or "Traceback" in line:
                        continue
                    else:
                        skipping_warning_block = False

                self.log(line)
                last_progress_line = None

            process.wait()
            return process.returncode

        except Exception as e:
            self.log(f"❌ Runtime error: {e}")
            return -1

        finally:
            self.current_process = None

    def convert_all_files(self):
        self.conversion_started = True
        VIDEO_EXTENSIONS = (
            ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".mpeg", ".mpg", ".mpe", ".mpv",
            ".m4v", ".3gp", ".3g2", ".ts", ".mts", ".m2ts", ".vob", ".f4v", ".f4p", ".f4a", ".f4b",
            ".rm", ".rmvb", ".asf", ".ogv", ".mxf", ".nsv", ".drc", ".yuv", ".viv", ".amv", ".str",
            ".qt", ".bik", ".bink", ".ivf", ".nuv", ".smk", ".mpg4", ".roq", ".thp", ".evo", ".dat",
            ".wtv", ".ismv", ".lsf", ".lsd", ".mng", ".dv", ".mv", ".tsv", ".vdr", ".m1v", ".m2v",
            ".cin", ".vc1", ".webp"
        )
        AUDIO_EXTENSIONS = (
            ".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".aiff", ".aif", ".alac", ".amr",
            ".wma", ".ac3", ".pcm", ".mp2", ".mp1", ".mka", ".ra", ".ram", ".dts", ".au", ".snd", ".oga",
            ".voc", ".caf", ".8svx", ".svx", ".wv", ".amb", ".cdda", ".mlp", ".ape", ".mpc", ".spx",
            ".tak", ".tta", ".gsm", ".gsm610", ".f32", ".f64", ".s16", ".s32", ".s8", ".u16", ".u32",
            ".u8", ".ircam", ".m3u", ".m3u8", ".mod", ".xm", ".it", ".s3m", ".ptm", ".stm"
        )
        self.currently_processing_entry = None

        try:
            while True:
                next_entry = next((f for f in self.file_queue if f['status'] not in ('done', 'processing', 'ignored', 'skipped')), None)
                if next_entry is None:
                    break

                if self.stop_requested:
                    self.log("⏹️ Conversion stopped by user.")
                    break

                total = len(self.file_queue)
                self.current_progress_idx = sum(1 for f in self.file_queue if f["status"] == "done")
                self.update_segmented_bar()
                self.progress_label.config(text=f"{self.current_progress_idx}/{total}")
                self.progress_total["maximum"] = total

                file_entry = next_entry
                self.currently_processing_entry = file_entry

                if file_entry not in self.file_queue:
                    self.log("⚠️ The current file was removed during conversion. Moving on to the next one.")
                    continue

                if not os.path.exists(file_entry['path']):
                    self.log(f"⚠️ Missing file, skipping {os.path.basename(file_entry['path'])}")
                    file_entry['status'] = 'skipped'
                    self.update_listbox_colors()
                    continue

                # skip if not supported
                ext = os.path.splitext(file_entry['path'])[1].lower()
                if ext not in VIDEO_EXTENSIONS and ext not in AUDIO_EXTENSIONS:
                    self.log(f"⛔ Skipping unsupported file type: {os.path.basename(file_entry['path'])}")
                    file_entry['status'] = 'skipped'
                    self.update_listbox_colors()
                    continue
                # --------------------------------------------------

                file_entry['status'] = 'processing'
                self.update_listbox_colors()
                self.update_segmented_bar()

                original_path = file_entry['path']
                is_video = ext in VIDEO_EXTENSIONS
                audio_path = original_path
                tmp_dir = None

                if is_video:
                    self.log(f"🎞️ Video detected, extracting audio...")
                    try:
                        tmp_dir = tempfile.mkdtemp()
                        audio_path = os.path.join(tmp_dir, "extracted.wav")
                        ffmpeg_cmd = [
                            "ffmpeg", "-y", "-i", original_path,
                            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", audio_path
                        ]
                        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    except Exception as e:
                        self.log(f"❌ Extraction audio error: {e}")
                        file_entry['status'] = 'skipped'
                        self.update_listbox_colors()
                        if tmp_dir:
                            shutil.rmtree(tmp_dir, ignore_errors=True)
                        continue

                base_midi_path = os.path.splitext(original_path)[0] + ".mid"
                midi_path = self.get_unique_output_path(base_midi_path)

                device = self.options.get("device", "cuda")
                self.log(f"➡️ Converting {os.path.basename(original_path)} with {device} ...")

                self.progress_file.start(10)
                try:
                    cmd = ["transkun", audio_path, midi_path, "--device", device]
                    if not self.options.get("use_eval", True):
                        cmd.append("--no-eval")
                    if not self.options.get("use_weights_only", True):
                        cmd.append("--no-weights-only")

                    ret = self.run_transkun_and_capture_progress(cmd)

                    if file_entry not in self.file_queue:
                        continue

                    if file_entry.get("status") == "ignored":
                        continue  

                    if ret == 0:
                        self.log(f"✅ Finished: {os.path.basename(midi_path)}")
                        file_entry['status'] = 'done'
                    elif ret == -1:
                        file_entry['status'] = 'pending'
                    elif ret == -2:
                        file_entry['status'] = 'skipped'
                        self.log(f"⛔ Skipped (deleted during processing): {os.path.basename(file_entry['path'])}")
                    else:
                        file_entry['status'] = 'pending'
                except subprocess.CalledProcessError as e:
                    self.log(f"❌ Conversion error: {e}")
                    file_entry['status'] = 'pending'
                except FileNotFoundError as e:
                    self.log(f"❌ Transkun not found: {e}")
                    file_entry['status'] = 'pending'
                except Exception as e:
                    self.log(f"❌ Unexpected error: {e}")
                    file_entry['status'] = 'pending'
                finally:
                    self.currently_processing_entry = None
                    self.progress_file.stop()
                    self.update_listbox_colors()
                    self.current_progress_idx = sum(1 for f in self.file_queue if f["status"] == "done")
                    self.update_segmented_bar()
                    self.progress_label.config(text=f"{self.current_progress_idx}/{len(self.file_queue)}")
                    self.progress_total["maximum"] = len(self.file_queue)

                    if tmp_dir:
                        shutil.rmtree(tmp_dir, ignore_errors=True)

        except Exception as e:
            self.log(f"❌ Fatal error during batch: {e}")
        finally:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.conversion_started = False
            self.current_progress_idx = sum(1 for f in self.file_queue if f["status"] == "done")
            total = len(self.file_queue)
            self.update_segmented_bar()
            if not self.stop_requested:
                self.log("🎉 Conversion done.")




    def open_advanced_options(self):
        opt_win = tk.Toplevel(self.root)
        opt_win.title("Advanced options")
        opt_win.resizable(False, False)
        opt_win.geometry("400x250")
        opt_win.grab_set()

        eval_var = tk.BooleanVar(value=self.options.get("use_eval", True))
        weights_var = tk.BooleanVar(value=self.options.get("use_weights_only", True))
        reentrant_var = tk.BooleanVar(value=self.options.get("use_reentrant", True))
        requires_grad_var = tk.BooleanVar(value=self.options.get("requires_grad", True))
        device_var = tk.StringVar(value=self.options.get("device", "cuda"))

        tk.Checkbutton(opt_win, text="Use model.eval() (eval mode)", variable=eval_var).pack(anchor="w", padx=15, pady=5)
        tk.Checkbutton(opt_win, text="Load model with weights_only=True (PyTorch security)", variable=weights_var).pack(anchor="w", padx=15, pady=5)
        tk.Checkbutton(opt_win, text="Use use_reentrant=True", variable=reentrant_var).pack(anchor="w", padx=15, pady=5)
        tk.Checkbutton(opt_win, text="Enable requires_grad=True", variable=requires_grad_var).pack(anchor="w", padx=15, pady=5)

        tk.Label(opt_win, text="Device for conversion :").pack(anchor="w", padx=15, pady=(10, 0))

        device_frame = tk.Frame(opt_win)
        device_frame.pack(anchor="w", padx=15)

        tk.Radiobutton(device_frame, text="CUDA (GPU)", variable=device_var, value="cuda").pack(side="left")
        tk.Radiobutton(device_frame, text="CPU", variable=device_var, value="cpu").pack(side="left")

        def save_and_close():
            self.options["use_eval"] = eval_var.get()
            self.options["use_weights_only"] = weights_var.get()
            self.options["use_reentrant"] = reentrant_var.get()
            self.options["requires_grad"] = requires_grad_var.get()
            self.options["device"] = device_var.get()
            save_options(self.options)
            self.log("💾 Advanced options saved.")
            self.log_options()
            opt_win.destroy()

        btn_save = tk.Button(opt_win, text="Save", command=save_and_close)
        btn_save.pack(pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = TranskunGUI(root)
    root.mainloop()
