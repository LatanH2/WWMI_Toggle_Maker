import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog


class DrawEntry:
    def __init__(
        self,
        comp,
        line_idx,
        comment,
        drawline,
        existing=False,
        if_start=None,
        if_end=None,
        var=None,
        status="",
    ):
        self.comp = comp
        self.line_idx = line_idx
        self.comment = comment
        self.drawline = drawline
        self.existing = existing  # True only for simple [E] toggles
        self.if_start = if_start
        self.if_end = if_end
        self.var = var
        self.status = status  # "", "E", "M"

    def display(self):
        tag = ""
        if self.status == "E":
            tag += "[E] "
        elif self.status == "M":
            tag += "[M] "
        c = self.comment.lstrip(";").strip() if self.comment else ""
        return f"{tag}C{self.comp} | L{self.line_idx+1} | {c} | {self.drawline.strip()}"


class ToggleSpec:
    def __init__(self, var, key, approx_idx, comment, drawline):
        self.var = var
        self.key = key
        self.approx_idx = approx_idx  # original index as hint
        self.comment = comment
        self.drawline = drawline


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("WWMI Toggle Maker")

        self.path_var = tk.StringVar()
        self.lines = []          # working copy of file
        self.entries = []        # type: list[DrawEntry]
        self.specs = []          # type: list[ToggleSpec]
        self.key_vars = set()    # variables that already have [Key..] sections
        self.modified = False    # True if Remove/Replace done without new specs

        self.build_ui()

    # ---------------- UI ----------------

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
        tk.Button(right, text="Remove Toggle", command=self.remove_toggle).pack(fill="x", pady=5)
        tk.Button(right, text="Clear Pending", command=self.clear_toggle).pack(fill="x", pady=5)

        self.status = tk.Label(right, text="0 pending")
        self.status.pack(fill="x", pady=8)

        tk.Button(right, text="Apply", command=self.apply).pack(fill="x", pady=5)

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[("INI files", "*.ini")])
        if p:
            self.path_var.set(p)

    # ---------------- SCAN ----------------

    def scan(self):
        p = self.path_var.get().strip()
        if not os.path.isfile(p):
            return

        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            self.lines = f.readlines()

        self.key_vars = self.find_key_vars(self.lines)
        self.entries = self.parse_draw(self.lines, self.key_vars)

        self.specs.clear()
        self.modified = False
        self.refresh()
        self.update_status()
        messagebox.showinfo("OK", f"{len(self.entries)} drawindexed found")

    @staticmethod
    def find_key_vars(lines):
        vars_found = set()
        sec_name = None
        for line in lines:
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                sec_name = s[1:-1]
                continue
            if sec_name and sec_name.lower().startswith("key"):
                m = re.search(r"\$(\w+)\s*=\s*0,1\b", s)
                if m:
                    vars_found.add(m.group(1))
        return vars_found

    @staticmethod
    def detect_toggle_blocks(lines, key_vars):
        toggle_map = {}
        n = len(lines)
        i = 0
        if_pat = re.compile(r"if\s+\$(\w+)\s*==\s*0\s*$", re.IGNORECASE)
        while i < n:
            s = lines[i].strip()
            m = if_pat.match(s)
            if not m:
                i += 1
                continue

            var = m.group(1)
            # find matching endif within same section
            j = i + 1
            end_idx = None
            while j < n:
                t = lines[j].strip()
                if t.lower() == "endif":
                    end_idx = j
                    break
                if t.startswith("[") and t.endswith("]"):
                    break
                j += 1

            if end_idx is None:
                i += 1
                continue

            # inspect body
            draw_indices = []
            mixed = False
            for k in range(i + 1, end_idx):
                t = lines[k].strip()
                if not t:
                    continue
                if t.startswith(";"):
                    continue
                if "drawindexed" in t and not t.startswith(";"):
                    draw_indices.append(k)
                else:
                    mixed = True

            if not draw_indices or var not in key_vars:
                i = end_idx + 1
                continue

            if not mixed and len(draw_indices) == 1:
                status = "E"
            else:
                status = "M"

            for k in draw_indices:
                toggle_map[k] = {
                    "var": var,
                    "if_start": i,
                    "if_end": end_idx,
                    "status": status,
                }

            i = end_idx + 1

        return toggle_map

    @staticmethod
    def parse_draw(lines, key_vars):
        res = []
        comp = None
        last_comment = None
        last_comment_idx = None
        pat = re.compile(r"\[TextureOverrideComponent(\d+)\]", re.I)

        toggle_map = App.detect_toggle_blocks(lines, key_vars)

        for i, line in enumerate(lines):
            s = line.strip()
            m = pat.match(s)
            if m:
                comp = int(m.group(1))
                last_comment = None
                last_comment_idx = None
                continue
            if comp is not None and s.startswith("[") and s.endswith("]"):
                comp = None
                last_comment = None
                last_comment_idx = None
                continue

            if comp is None:
                continue

            if s.startswith(";"):
                last_comment = line
                last_comment_idx = i
                continue

            if "drawindexed" in s and not s.startswith(";"):
                info = toggle_map.get(i)
                if info:
                    status = info["status"]
                    existing = status == "E"
                    var = info["var"]
                    if_start = info["if_start"]
                    if_end = info["if_end"]
                else:
                    status = ""
                    existing = False
                    var = None
                    if_start = None
                    if_end = None

                res.append(
                    DrawEntry(
                        comp=comp,
                        line_idx=i,
                        comment=last_comment,
                        drawline=line,
                        existing=existing,
                        if_start=if_start,
                        if_end=if_end,
                        var=var,
                        status=status,
                    )
                )

        return res

    # ---------------- LIST / STATUS ----------------

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for e in self.entries:
            mark = ""
            if any(s.approx_idx == e.line_idx for s in self.specs):
                mark += "[T] "
            if e.status == "E":
                mark += "[E] "
            elif e.status == "M":
                mark += "[M] "
            self.listbox.insert(tk.END, mark + e.display())

    def update_status(self):
        self.status.config(text=f"{len(self.specs)} pending")

    def clear_toggle(self):
        self.specs.clear()
        self.update_status()
        self.refresh()

    # ---------------- REMOVE / ADD ----------------

    def remove_toggle(self):
        sel = self.listbox.curselection()
        if not sel:
            return

        changed = False
        for i in sel:
            entry = self.entries[i]
            if entry.status == "M":
                # complex toggle: don't auto-edit
                continue
            if entry.existing:
                self.delete_existing(entry)
                changed = True

        if changed:
            self.refresh()
            self.modified = True

    def add_toggle(self):
        sel = self.listbox.curselection()
        if not sel:
            return

        # check if any selected have simple existing toggle
        need_replace = any(self.entries[i].existing for i in sel)
        if need_replace:
            if not messagebox.askyesno(
                "Toggle Exists",
                "One or more selected drawindexed already have a toggle.\n"
                "Replace existing toggle(s) with a new one?",
            ):
                return
            for i in sel:
                e = self.entries[i]
                if e.existing:
                    self.delete_existing(e)
            self.modified = True

        var = simpledialog.askstring("Var Name", "Var name (without $):")
        if not var:
            return
        key = simpledialog.askstring("Key Name", "Keyboard key:")
        if not key:
            return

        var = var.strip()
        key = key.strip()

        for i in sel:
            e = self.entries[i]
            self.specs.append(
                ToggleSpec(
                    var=var,
                    key=key,
                    approx_idx=e.line_idx,
                    comment=e.comment,
                    drawline=e.drawline,
                )
            )

        self.refresh()
        self.update_status()

    def delete_existing(self, entry: DrawEntry):
        if not entry.existing:
            return

        if entry.if_start is None or entry.if_end is None:
            entry.existing = False
            entry.status = ""
            entry.var = None
            return

        idx = entry.if_start
        end = entry.if_end

        # capture original block
        block = self.lines[idx : end + 1]

        # inside-block, find the drawindexed and optional comment directly above it
        draw_idx = None
        for rel, line in enumerate(block):
            t = line.strip()
            if "drawindexed" in t and not t.startswith(";"):
                draw_idx = idx + rel
                break

        comment_line = None
        if draw_idx is not None and draw_idx - 1 >= idx:
            prev = self.lines[draw_idx - 1]
            if prev.strip().startswith(";"):
                comment_line = prev

        # remove whole if..endif block
        for _ in range(end - idx + 1):
            self.lines.pop(idx)

        # restore comment + drawindexed at original position
        insert_at = idx
        if comment_line is not None:
            self.lines.insert(insert_at, comment_line)
            insert_at += 1

        self.lines.insert(insert_at, entry.drawline)

        # mark as no longer toggled
        entry.existing = False
        entry.status = ""
        entry.var = None
        entry.if_start = None
        entry.if_end = None
        entry.line_idx = insert_at

        # per-variable cleanup will be handled at the end by prune_unused_toggles

    # ---------------- APPLY ----------------

    def apply(self):
        if not self.specs and not self.modified:
            messagebox.showwarning("Nothing to Apply", "No pending changes detected.")
            return

        p = self.path_var.get().strip()
        if not p:
            return

        shutil.copy2(p, p + ".bak")

        out = list(self.lines)

        if self.specs:
            out = self.wrap_draw(out, self.specs)
            out = self.insert_constants(out, self.specs)
            out = self.insert_keys(out, self.specs)

        # final cleanup pass: remove unused toggle vars and key sections
        out = self.prune_unused_toggles(out)

        with open(p, "w", encoding="utf-8") as f:
            f.writelines(out)

        messagebox.showinfo("Done", "Backup saved.\nChanges applied.")
        self.modified = False
        self.specs.clear()
        self.update_status()

    # ---------------- INSERT CONSTANTS / KEYS ----------------

    @staticmethod
    def insert_constants(lines, specs):
        lines = list(lines)
        const_idx = next(
            (i for i, l in enumerate(lines) if l.strip().lower() == "[constants]"),
            None,
        )

        if const_idx is None:
            # create [Constants] at top
            lines = ["[Constants]\n", "\n"] + lines
            const_idx = 0

        end = next(
            (
                i
                for i in range(const_idx + 1, len(lines))
                if lines[i].strip().startswith("[")
                and lines[i].strip().endswith("]")
            ),
            len(lines),
        )

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

        return lines

    @staticmethod
    def insert_keys(lines, specs):
        lines = list(lines)

        # collect existing key vars
        existing_key_vars = set()
        for l in lines:
            s = l.strip()
            m = re.match(r"\[Key(\w+)\]", s, re.IGNORECASE)
            if m:
                existing_key_vars.add(m.group(1))
        # also look for "$var = 0,1" inside sections
        for l in lines:
            s = l.strip()
            m = re.search(r"\$(\w+)\s*=\s*0,1\b", s)
            if m:
                existing_key_vars.add(m.group(1))

        # find [Constants]
        const_idx = next(
            (i for i, l in enumerate(lines) if l.strip().lower() == "[constants]"),
            None,
        )
        if const_idx is None:
            const_idx = 0

        # first section after [Constants]
        first_after_const = next(
            (
                i
                for i in range(const_idx + 1, len(lines))
                if lines[i].strip().startswith("[")
                and lines[i].strip().endswith("]")
            ),
            len(lines),
        )

        # end of last [Key...] section
        last_key_end = None
        i = first_after_const
        while i < len(lines):
            s = lines[i].strip()
            if s.startswith("[") and s.endswith("]"):
                name = s[1:-1]
                if name.lower().startswith("key"):
                    j = i + 1
                    while j < len(lines) and not (
                        lines[j].strip().startswith("[")
                        and lines[j].strip().endswith("]")
                    ):
                        j += 1
                    last_key_end = j
                    i = j
                    continue
            i += 1

        if last_key_end is None:
            insert_pos = first_after_const
        else:
            insert_pos = last_key_end

        # build new key sections
        var_to_key = {}
        for s in specs:
            var_to_key[s.var] = s.key

        key_lines = []
        for var, key in var_to_key.items():
            if var in existing_key_vars:
                continue
            key_lines += [
                "\n",
                f"[Key{var}]\n",
                "condition = $object_detected\n",
                f"key = {key}\n",
                "type = cycle\n",
                f"${var} = 0,1\n",
            ]

        if not key_lines:
            return lines

        return lines[:insert_pos] + key_lines + lines[insert_pos:]

    # ---------------- WRAP DRAW ----------------

    @staticmethod
    def _find_draw_index(lines, spec: ToggleSpec):
        """Locate the current index of the target drawindexed line.
        Prefer the occurrence closest to spec.approx_idx."""
        target = spec.drawline.strip()
        candidates = [i for i, l in enumerate(lines) if l.strip() == target]
        if not candidates:
            return None
        return min(candidates, key=lambda i: abs(i - spec.approx_idx))

    @staticmethod
    def wrap_draw(lines, specs):
        new = list(lines)

        for s in sorted(specs, key=lambda x: x.approx_idx, reverse=True):
            idx = App._find_draw_index(new, s)
            if idx is None:
                continue

            drawline = new[idx]

            comment_line = None
            comment_idx = None
            j = idx - 1
            while j >= 0 and new[j].strip() == "":
                j -= 1
            if j >= 0 and new[j].strip().startswith(";"):
                comment_line = new[j]
                comment_idx = j

            if comment_idx is not None and comment_idx < idx:
                new.pop(idx)         # draw
                new.pop(comment_idx) # comment
                insert_at = comment_idx
            else:
                new.pop(idx)
                insert_at = idx

            raw = drawline.rstrip("\n")
            indent = raw[: len(raw) - len(raw.lstrip())]
            base = raw.strip()

            block = []
            block.append(f"{indent}if ${s.var} == 0\n")

            if comment_line is not None:
                c = comment_line.lstrip()
                if not c.endswith("\n"):
                    c += "\n"
                block.append(indent + "    " + c.lstrip())

            block.append(f"{indent}    {base}\n")
            block.append(f"{indent}endif\n")

            new = new[:insert_at] + block + new[insert_at:]

        return new

    # ---------------- FINAL CLEANUP ----------------

    @staticmethod
    def prune_unused_toggles(lines):
        used_vars = set()
        if_pat = re.compile(r"\bif\s+\$(\w+)\s*==\s*0\b", re.IGNORECASE)

        for line in lines:
            m = if_pat.search(line)
            if m:
                used_vars.add(m.group(1))

        out = list(lines)

        const_idx = next(
            (i for i, l in enumerate(out) if l.strip().lower() == "[constants]"),
            None,
        )
        if const_idx is not None:
            end = next(
                (
                    i
                    for i in range(const_idx + 1, len(out))
                    if out[i].strip().startswith("[")
                    and out[i].strip().endswith("]")
                ),
                len(out),
            )
            for i in range(end - 1, const_idx - 1, -1):
                m = re.search(r"persist\s+\$(\w+)", out[i])
                if m and m.group(1) not in used_vars:
                    out.pop(i)

        i = 0
        while i < len(out):
            line = out[i].strip()
            if line.lower().startswith("[key"):
                j = i + 1
                key_var = None
                while j < len(out) and not (
                    out[j].strip().startswith("[") and out[j].strip().endswith("]")
                ):
                    m = re.search(r"\$(\w+)\s*=\s*0,1\b", out[j])
                    if m:
                        key_var = m.group(1)
                    j += 1
                if key_var is not None and key_var not in used_vars:
                    del out[i:j]
                    continue
            i += 1

        return out


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
