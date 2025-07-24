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

        # Frame liste fichiers + boutons
        frame_list = tk.Frame(root)
        frame_list.pack(padx=10, pady=5, fill="x")

        tk.Label(frame_list, text="File List (order) :").pack(anchor="w")

        self.listbox = tk.Listbox(frame_list, height=8, activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)

        # Events de drag & drop
        self.listbox.bind("<Button-1>", self.on_drag_start)
        self.listbox.bind("<B1-Motion>", self.on_drag_motion)
        self.listbox.bind("<ButtonRelease-1>", self.on_drag_release)

        scrollbar = tk.Scrollbar(frame_list, command=self.listbox.yview)
        scrollbar.pack(side="left", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        frame_buttons = tk.Frame(frame_list)
        frame_buttons.pack(side="left", padx=5)

        tk.Button(frame_buttons, text="Add file", command=self.add_files).pack(fill="x", pady=2)
        tk.Button(frame_buttons, text="Delete selected file", command=self.remove_selected).pack(fill="x", pady=2)
        tk.Button(frame_buttons, text="Delete all files", command=self.clear_list).pack(fill="x", pady=2)

        # Bouton Options avancées
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


        self.progress_canvas.bind("<Configure>", lambda e: self.update_segmented_bar(self.current_progress_idx, len(self.file_queue)))

        self.progress_label = tk.Label(frame_progress, text="0/0")
        self.progress_label.pack(anchor="e", padx=5)


        # Console logs
        tk.Label(root, text="").pack(anchor="w", padx=10)
        self.text_console = tk.Text(root, height=10, bg="white", fg="black", state=tk.DISABLED)
        self.text_console.pack(padx=10, pady=5, fill="both", expand=True)

        # start/stop
        frame_controls = tk.Frame(root)
        frame_controls.pack(pady=10)

        self.btn_start = tk.Button(frame_controls, text="Start Transkun", command=self.start_conversion, bg="green", fg="white", width=20)
        self.btn_start.pack(side="left", padx=5)

        self.btn_stop = tk.Button(frame_controls, text="Stop", command=self.stop_conversion, bg="red", fg="white", width=20, state=tk.DISABLED)
        self.btn_stop.pack(side="left", padx=5)

        # display options at start
        self.log_options()

    def update_segmented_bar(self, current_idx, total):
        self.progress_canvas.delete("all")
        if total == 0:
            return

        width = self.progress_canvas.winfo_width()
        segment_width = width / total
        for i in range(total):
            x0 = i * segment_width
            x1 = (i + 1) * segment_width

            if current_idx == -1:
                color = "lightgray"  # pas encore commencé
            elif i < current_idx:
                color = "green"  # déjà fait
            elif i == current_idx:
                color = "orange"  # en cours
            else:
                color = "lightgray"  # à venir


            self.progress_canvas.create_rectangle(x0, 0, x1, 20, fill=color, outline="black")

    def update_listbox_colors(self, current_idx):
        for i in range(len(self.file_queue)):
            if i < current_idx:
                self.listbox.itemconfig(i, {'fg': 'green'})
            elif i == current_idx:
                self.listbox.itemconfig(i, {'fg': 'orange'})
            else:
                self.listbox.itemconfig(i, {'fg': 'black'})

    # Drag and Drop in list file
    def on_drag_start(self, event):
        self.drag_start_index = self.listbox.nearest(event.y)
        self.drag_current_index = self.drag_start_index

    def on_drag_motion(self, event):
        target_index = self.listbox.nearest(event.y)

        # if forbidden
        if target_index <= self.current_progress_idx:
            target_index = self.drag_current_index  # stay on last valid position

        if target_index != self.drag_current_index:
            self.drag_current_index = target_index
            # display update
            self.listbox.selection_clear(0, 'end')
            self.listbox.selection_set(self.drag_start_index)
            self.listbox.activate(self.drag_start_index)


    def on_drag_release(self, event):
        target_index = self.listbox.nearest(event.y)

        if target_index <= self.current_progress_idx:
            # cancel move if forbiden
            target_index = self.drag_start_index

        if target_index != self.drag_start_index:
            self.file_queue[self.drag_start_index], self.file_queue[target_index] = \
                self.file_queue[target_index], self.file_queue[self.drag_start_index]
            self.update_listbox()

        # reset
        self.drag_start_index = None
        self.drag_current_index = None
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(target_index)
        self.listbox.activate(target_index)

    def update_listbox(self):
        self.listbox.delete(0, tk.END)
        for idx, path in enumerate(self.file_queue, 1):
            self.listbox.insert(tk.END, f"{idx}. {os.path.basename(path)}")
        self.update_listbox_colors(self.current_progress_idx)


    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Add file",
            filetypes=[
                ("All Files", "*.*")
            ]
        )

        for f in files:
            if f not in self.file_queue:
                self.file_queue.append(f)
        self.update_listbox()

    def remove_selected(self):
        selected = list(self.listbox.curselection())
        for index in reversed(selected):
            del self.file_queue[index]
        self.update_listbox()

    def clear_list(self):
        self.file_queue.clear()
        self.update_listbox()

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

    def start_conversion(self):
        if not self.file_queue:
            messagebox.showwarning("No file", "add file to convert.")
            return
        self.stop_requested = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        self.current_progress_idx = 0
        self.update_listbox_colors(0)
        self.update_segmented_bar(0, len(self.file_queue))


        threading.Thread(target=self.convert_all_files, daemon=True).start()

    def stop_conversion(self):
        if messagebox.askyesno("STOP", "Confirm ?"):
            self.stop_requested = True
            self.btn_stop.config(state=tk.DISABLED)
            self.log("⏳ Stop task : conversions will stop after this current conversion")

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

            last_progress_line = None
            skipping_warning_block = False

            for raw_line in process.stdout:
                line = raw_line.rstrip()

                if not line.strip():
                    continue

                # Detection progress bar
                if line.startswith("[Transkun] Progression:"):
                    percent_pos = line.find('%')
                    if percent_pos != -1:
                        line = line[:percent_pos + 1]

                    # display only in line change
                    if line != last_progress_line:
                        if last_progress_line is None:
                            self.log(line)
                        else:
                            self.log_replace_last(line)
                        last_progress_line = line

                    skipping_warning_block = False
                    continue

                # Detection warning
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
                    # intended or warning = skip
                    if line.startswith("  ") or line.strip().endswith(")") or "Traceback" in line:
                        continue
                    else:
                        skipping_warning_block = False  

                # normal logs (➡️ Converting, ✅ Finished, etc.)
                self.log(line)
                last_progress_line = None  # reset to avoid accidental replace

            process.wait()
            return process.returncode

        except Exception as e:
            self.log(f"❌ Erreur d'exécution: {e}")
            return -1


    def convert_all_files(self):
        total = len(self.file_queue)
        self.current_progress_idx = 0
        self.update_segmented_bar(0, total)
        self.progress_total["maximum"] = total
        self.progress_label.config(text=f"0/{total}")

        VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm")

        try:
            for idx, original_path in enumerate(self.file_queue):
                if self.stop_requested:
                    self.log("⏹️ Conversion stopped by user.")
                    break

                ext = os.path.splitext(original_path)[1].lower()
                is_video = ext in VIDEO_EXTENSIONS
                audio_path = original_path  
                tmp_dir = None

                # extract audio if video
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
                    if ret == 0:
                        self.log(f"✅ Finished: {os.path.basename(midi_path)}")
                    else:
                        self.log(f"❌ Conversion error: Transkun exited with code {ret}")

                except subprocess.CalledProcessError as e:
                    self.log(f"❌ Conversion error: {e}")
                except FileNotFoundError as e:
                    self.log(f"❌ Transkun not found: {e}")
                except Exception as e:
                    self.log(f"❌ Unexpected error: {e}")
                finally:
                    self.progress_file.stop()
                    self.current_progress_idx = idx + 1
                    self.update_listbox_colors(self.current_progress_idx)
                    self.update_segmented_bar(self.current_progress_idx, total)
                    self.progress_label.config(text=f"{idx + 1}/{total}")
                    if tmp_dir:
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                    if is_video:
                        shutil.rmtree(tmp_dir, ignore_errors=True)

        except Exception as e:
            self.log(f"❌ Fatal error during batch: {e}")
        finally:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            if not self.stop_requested:
                self.log("🎉 Conversion done.")


    def open_advanced_options(self):
        opt_win = tk.Toplevel(self.root)
        opt_win.title("Advanced options (normal user don't need)")
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
