import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog


class DrawEntry:
    def __init__(self, comp, line_idx, comment, drawline):
        self.comp = comp
        self.line_idx = line_idx
        self.comment = comment
        self.drawline = drawline

    def display(self):
        c = self.comment.lstrip(";").strip() if self.comment else ""
        return f"C{self.comp} | L{self.line_idx+1} | {c} | {self.drawline.strip()}"


class ToggleSpec:
    def __init__(self, var, key, line_idx, comment):
        self.var = var
        self.key = key
        self.line_idx = line_idx
        self.comment = comment


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("WWMI Toggle Maker")

        self.path_var = tk.StringVar()
        self.lines = []
        self.entries = []
        self.specs = []

        self.build_ui()

    def build_ui(self):
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)

        tk.Label(top, text="mod.ini:").pack(side="left")
        tk.Entry(top, textvariable=self.path_var, width=60).pack(side="left", padx=5)
        tk.Button(top, text="Browse", command=self.browse).pack(side="left")
        tk.Button(top, text="Scan", command=self.scan).pack(side="left", padx=5)

        mid = tk.Frame(self.root)
        mid.pack(fill="both", expand=True, padx=8)

        self.listbox = tk.Listbox(mid, selectmode="extended", width=100)
        self.listbox.pack(side="left", fill="both", expand=True)

        scroll = tk.Scrollbar(mid, command=self.listbox.yview)
        scroll.pack(side="left", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)

        right = tk.Frame(mid)
        right.pack(side="left", fill="y", padx=6)

        tk.Button(right, text="Add Toggle", command=self.add_toggle).pack(fill="x", pady=5)
        tk.Button(right, text="Clear All", command=self.clear_toggle).pack(fill="x", pady=5)
        self.status = tk.Label(right, text="0 pending")
        self.status.pack(fill="x", pady=8)
        tk.Button(right, text="Apply", command=self.apply).pack(fill="x", pady=5)

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[("INI files", "*.ini")])
        if p:
            self.path_var.set(p)

    def scan(self):
        p = self.path_var.get().strip()
        if not os.path.isfile(p):
            return

        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            self.lines = f.readlines()

        self.entries = self.parse_draw(self.lines)
        self.specs.clear()
        self.refresh()
        self.update_status()
        messagebox.showinfo("OK", f"{len(self.entries)} drawindexed found")

    @staticmethod
    def parse_draw(lines):
        res = []
        comp = None
        last_comment = None
        pat = re.compile(r"\[TextureOverrideComponent(\d+)\]", re.I)

        for i, line in enumerate(lines):
            s = line.strip()
            m = pat.match(s)
            if m:
                comp = int(m.group(1))
                last_comment = None
                continue
            if comp is not None and s.startswith("[") and s.endswith("]"):
                comp = None
                last_comment = None
                continue

            if comp is None:
                continue

            if s.startswith(";"):
                last_comment = line
                continue

            if "drawindexed" in s and not s.startswith(";"):
                res.append(DrawEntry(comp, i, last_comment, line))

        return res

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for e in self.entries:
            mark = "[T] " if any(s.line_idx == e.line_idx for s in self.specs) else ""
            self.listbox.insert(tk.END, mark + e.display())

    def add_toggle(self):
        sel = self.listbox.curselection()
        if not sel:
            return

        var = simpledialog.askstring("Var Name", "Var (no $):")
        if not var:
            return
        key = simpledialog.askstring("Key Name", "Key:")
        if not key:
            return

        var, key = var.strip(), key.strip()

        for i in sel:
            e = self.entries[i]
            self.specs = [s for s in self.specs if s.line_idx != e.line_idx]
            self.specs.append(ToggleSpec(var, key, e.line_idx, e.comment))

        self.refresh()
        self.update_status()

    def clear_toggle(self):
        self.specs.clear()
        self.refresh()
        self.update_status()

    def update_status(self):
        self.status.config(text=f"{len(self.specs)} pending")

    def apply(self):
        if not self.specs:
            return
        p = self.path_var.get().strip()
        if not p:
            return

        shutil.copy2(p, p + ".bak")

        out = self.apply_all(self.lines, self.specs)

        with open(p, "w", encoding="utf-8") as f:
            f.writelines(out)

        messagebox.showinfo("Done", "Backup saved\nChanges applied")

    @staticmethod
    def apply_all(lines, specs):
        out = list(lines)
        # 1) wrap drawindexed first (line indexes based on original file)
        out = App.wrap_draw(out, specs)
        # 2) then add constants/keys at top
        out = App.insert_constants(out, specs)
        out = App.insert_keys(out, specs)
        return out

    @staticmethod
    def insert_constants(lines, specs):
        lines = list(lines)

        const_idx = next((i for i, l in enumerate(lines)
                          if l.strip().lower() == "[constants]"), None)

        if const_idx is None:
            lines = ["[Constants]\n", "\n"] + lines
            const_idx = 0

        end = next((i for i in range(const_idx + 1, len(lines))
                    if lines[i].strip().startswith("[") and lines[i].strip().endswith("]")),
                   len(lines))

        exist = set()
        for i in range(const_idx, end):
            m = re.search(r"persist\s+\$(\w+)", lines[i])
            if m:
                exist.add(m.group(1))

        new_vars = []
        seen = set()
        for s in specs:
            if s.var not in exist and s.var not in seen:
                new_vars.append(f"global persist ${s.var} = 0\n")
                seen.add(s.var)

        if new_vars:
            lines = lines[:end] + new_vars + lines[end:]
            end += len(new_vars)

        return lines

    @staticmethod
    def insert_keys(lines, specs):
        lines = list(lines)
        const_idx = next((i for i, l in enumerate(lines)
                          if l.strip().lower() == "[constants]"), 0)

        end = next((i for i in range(const_idx + 1, len(lines))
                    if lines[i].strip().startswith("[") and lines[i].strip().endswith("]")),
                   len(lines))

        m = {}
        for s in specs:
            m[s.var] = s.key

        key_lines = []
        for var, key in m.items():
            key_lines += [
                "\n",
                f"[Key{var}]\n",
                "condition = $object_detected\n",
                f"key = {key}\n",
                "type = cycle\n",
                f"${var} = 0,1\n",
            ]

        lines = lines[:end] + ["\n"] + key_lines + ["\n"] + lines[end:]
        return lines

    @staticmethod
    def wrap_draw(lines, specs):
        new = list(lines)

        # process from bottom to top
        for s in sorted(specs, key=lambda x: x.line_idx, reverse=True):
            idx = s.line_idx
            if idx < 0 or idx >= len(new):
                continue

            drawline = new[idx]

            # find attached comment just above, if any
            comment_idx = None
            if s.comment:
                comment_text = s.comment.strip()
                j = idx - 1
                while j >= 0 and new[j].strip() == "":
                    j -= 1
                if j >= 0 and new[j].strip() == comment_text:
                    comment_idx = j

            # remove draw line and optional comment line (from bottom)
            if comment_idx is not None and comment_idx < idx:
                # remove draw first
                new.pop(idx)
                # then comment
                new.pop(comment_idx)
                insert_at = comment_idx
            else:
                new.pop(idx)
                insert_at = idx

            # base indent from original drawindexed line
            raw = drawline.rstrip("\n")
            indent = raw[:len(raw) - len(raw.lstrip())]
            base = raw.strip()

            block = []

            # if line
            block.append(f"{indent}if ${s.var} == 0\n")

            # comment inside if (if exists)
            if comment_idx is not None and s.comment:
                c = s.comment.lstrip()
                if not c.endswith("\n"):
                    c += "\n"
                block.append(indent + "    " + c.lstrip())

            # drawindexed inside if
            block.append(f"{indent}    {base}\n")

            # endif
            block.append(f"{indent}endif\n")

            new = new[:insert_at] + block + new[insert_at:]

        return new


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
