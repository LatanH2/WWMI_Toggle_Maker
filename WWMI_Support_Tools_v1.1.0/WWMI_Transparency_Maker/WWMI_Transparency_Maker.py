import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog


class TransparencyTool:
    def __init__(self, root):
        self.root = root
        self.root.title("WWMI Transparency Maker")

        self.ini_path = None
        self.component_draws = {}
        self.pending_changes = []
        self.next_shader_index = 1

        self._build_ui()

    def _build_ui(self):
        file_frame = tk.Frame(self.root)
        file_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(file_frame, text="mod.ini path:").pack(side="left")

        self.entry_path = tk.Entry(file_frame, width=60)
        self.entry_path.pack(side="left", padx=5)

        btn_browse = tk.Button(file_frame, text="Browse...", command=self.browse_ini)
        btn_browse.pack(side="left")

        btn_scan = tk.Button(file_frame, text="Scan", command=self.scan_ini)
        btn_scan.pack(side="left", padx=5)

        list_frame = tk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tk.Label(list_frame, text="Component - drawindexed:").pack(anchor="w")

        self.list_all = tk.Listbox(list_frame, height=18)
        self.list_all.pack(fill="both", expand=True, side="left")

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.list_all.yview)
        scrollbar.pack(side="right", fill="y")
        self.list_all.config(yscrollcommand=scrollbar.set)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=10)

        btn_add = tk.Button(btn_frame, text="Add Transparency", command=self.add_transparency)
        btn_add.pack(side="left")

        btn_apply = tk.Button(btn_frame, text="Apply", command=self.apply_changes)
        btn_apply.pack(side="right")

        self.status_label = tk.Label(self.root, text="Select mod.ini and scan.", anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=(0, 10))

    def browse_ini(self):
        path = filedialog.askopenfilename(
            title="Select mod.ini",
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")]
        )
        if path:
            self.ini_path = path
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, path)
            self.scan_ini()

    def scan_ini(self):
        path = self.entry_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Error", "Invalid mod.ini file path.")
            return

        self.ini_path = path
        self.component_draws.clear()
        self.pending_changes.clear()

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except:
            with open(path, "r", encoding="cp949", errors="ignore") as f:
                lines = f.readlines()

        self.next_shader_index = self._scan_existing_shader_index(lines)

        current_comp = None
        last_comment = None
        pattern_comp = re.compile(r"^\[TextureOverrideComponent(\d+)\]", re.IGNORECASE)
        pattern_draw = re.compile(r"^drawindexed\s*=\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$", re.IGNORECASE)

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if lower.startswith(";"):
                last_comment = stripped.lstrip(";").strip()
                continue

            m_comp = pattern_comp.match(stripped)
            if m_comp:
                current_comp = int(m_comp.group(1))
                self.component_draws.setdefault(current_comp, [])
                last_comment = None
                continue

            if current_comp is not None and lower.startswith("drawindexed"):
                m_draw = pattern_draw.match(stripped)
                if m_draw:
                    params = tuple(map(int, m_draw.groups()))
                    self.component_draws[current_comp].append({
                        "params": params,
                        "line_text": line.rstrip("\n"),
                        "comment": last_comment or ""
                    })
                    last_comment = None

        self.list_all.delete(0, tk.END)
        for comp in sorted(self.component_draws.keys()):
            for entry in self.component_draws[comp]:
                a, b, c = entry["params"]
                comment = entry["comment"]
                disp = f"Component {comp}"
                if comment:
                    disp += f" — {comment}"
                disp += f" — drawindexed = {a}, {b}, {c}"
                self.list_all.insert(tk.END, disp)

        self.status_label.config(text="Scan complete.")

    def _scan_existing_shader_index(self, lines):
        pattern = re.compile(r"^\[CustomShaderTransparency(\d+)\]", re.IGNORECASE)
        max_i = 0
        for line in lines:
            m = pattern.match(line.strip())
            if m:
                idx = int(m.group(1))
                max_i = max(max_i, idx)
        return max_i + 1

    def get_selected_draw(self):
        sel = self.list_all.curselection()
        if not sel:
            messagebox.showerror("Error", "Select a drawindexed entry.")
            return None, None, None

        line = self.list_all.get(sel[0])
        m = re.search(r"Component\s+(\d+)\s+—(?:\s+(.+?)\s+—)?\s*drawindexed\s*=\s*(\d+),\s*(\d+),\s*(\d+)", line)
        if not m:
            return None, None, None

        comp = int(m.group(1))
        comment = m.group(2) if m.group(2) else ""
        params = (int(m.group(3)), int(m.group(4)), int(m.group(5)))
        return comp, params, comment

    def ask_mode(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Select mode")
        dialog.grab_set()

        var = tk.StringVar(value="")
        tk.Label(dialog, text="Select transparency mode:").pack(padx=10, pady=10)

        def set_alpha():
            var.set("alpha")
            dialog.destroy()

        def set_factor():
            var.set("factor")
            dialog.destroy()

        frame = tk.Frame(dialog)
        frame.pack(padx=10, pady=10)
        tk.Button(frame, text="Texture Alpha Based", width=22, command=set_alpha).pack(side="left", padx=5)
        tk.Button(frame, text="Blend Factor Based", width=22, command=set_factor).pack(side="left", padx=5)

        dialog.wait_window()
        val = var.get()
        return val if val in ("alpha", "factor") else None

    def ask_factors(self):
        arr = []
        for i in range(4):
            v = simpledialog.askstring(
                "Blend Factor",
                f"Enter blend_factor[{i}] (0.0-1.0):",
                parent=self.root
            )
            if v is None:
                return None
            v = v.strip()
            try:
                float(v)
            except:
                messagebox.showerror("Error", "Invalid value.")
                return None
            arr.append(v)
        return arr

    def add_transparency(self):
        comp, params, comment = self.get_selected_draw()
        if comp is None:
            return

        mode = self.ask_mode()
        if not mode:
            return

        factors = None
        if mode == "factor":
            factors = self.ask_factors()
            if factors is None:
                return

        existing_idx = None
        for i, ch in enumerate(self.pending_changes):
            if ch["component"] == comp and ch["params"] == params:
                existing_idx = i
                break

        if existing_idx is not None:
            ans = messagebox.askyesno("Overwrite", "Already queued. Overwrite?")
            if not ans:
                return
            shader_name = self.pending_changes[existing_idx]["shader_name"]
            self.pending_changes[existing_idx] = {
                "component": comp,
                "params": params,
                "comment": comment,
                "mode": mode,
                "factors": factors,
                "shader_name": shader_name,
            }
        else:
            shader_name = f"CustomShaderTransparency{self.next_shader_index}"
            self.next_shader_index += 1
            self.pending_changes.append({
                "component": comp,
                "params": params,
                "comment": comment,
                "mode": mode,
                "factors": factors,
                "shader_name": shader_name,
            })

        self.status_label.config(text="Transparency queued.")

    def apply_changes(self):
        if not self.ini_path:
            messagebox.showerror("Error", "No INI loaded.")
            return
        if not self.pending_changes:
            messagebox.showinfo("Info", "No changes queued.")
            return

        try:
            with open(self.ini_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except:
            with open(self.ini_path, "r", encoding="cp949", errors="ignore") as f:
                lines = f.readlines()

        backup = self.ini_path + ".bak"
        with open(backup, "w", encoding="utf-8") as fbak:
            fbak.writelines(lines)

        pattern_comp = re.compile(r"^\[TextureOverrideComponent(\d+)\]", re.IGNORECASE)
        pattern_draw = re.compile(r"^(\s*)drawindexed\s*=\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$", re.IGNORECASE)

        new_lines = []
        shader_sections = []
        current_comp = None

        pending_map = {(ch["component"], ch["params"]): ch for ch in self.pending_changes}

        for line in lines:
            stripped = line.strip()
            m_comp = pattern_comp.match(stripped)

            if m_comp:
                if current_comp is not None:
                    for sec in shader_sections:
                        new_lines.extend(sec)
                    shader_sections = []

                current_comp = int(m_comp.group(1))
                new_lines.append(line)
                continue

            m_draw = pattern_draw.match(line)
            if m_draw and current_comp is not None:
                indent = m_draw.group(1)
                params = (int(m_draw.group(2)), int(m_draw.group(3)), int(m_draw.group(4)))

                key = (current_comp, params)
                if key in pending_map:
                    ch = pending_map[key]
                    orig = line.rstrip("\n")
                    commented = f"{indent}; {orig.lstrip()}\n"
                    new_lines.append(commented)
                    new_lines.append(f"{indent}run = {ch['shader_name']}\n")
                    shader_sections.append(self._build_shader_section(ch))
                    del pending_map[key]
                    continue

            if stripped.startswith("[") and stripped.endswith("]") and current_comp is not None:
                for sec in shader_sections:
                    new_lines.extend(sec)
                shader_sections = []
                current_comp = None
                new_lines.append(line)
                continue

            new_lines.append(line)

        if current_comp is not None:
            for sec in shader_sections:
                new_lines.extend(sec)

        with open(self.ini_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        self.status_label.config(text="Done. Backup created.")
        messagebox.showinfo("Success", "Changes applied.\nBackup: mod.ini.bak")

    def _build_shader_section(self, ch):
        comp = ch["component"]
        a, b, c = ch["params"]
        mode = ch["mode"]
        factors = ch["factors"]
        name = ch["shader_name"]

        out = []
        out.append("\n")
        out.append(f"[{name}]\n")
        if ch["comment"]:
            out.append(f"; {ch['comment']}\n")
        if mode == "alpha":
            out.append("blend = ADD SRC_ALPHA INV_SRC_ALPHA\n")
        else:
            out.append("blend = ADD BLEND_FACTOR INV_BLEND_FACTOR\n")
            out.append(f"blend_factor[0] = {factors[0]}\n")
            out.append(f"blend_factor[1] = {factors[1]}\n")
            out.append(f"blend_factor[2] = {factors[2]}\n")
            out.append(f"blend_factor[3] = {factors[3]}\n")

        out.append(f"drawindexed = {a}, {b}, {c}\n")
        return out


def main():
    root = tk.Tk()
    app = TransparencyTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
