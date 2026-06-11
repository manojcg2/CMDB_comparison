import os
import re
import sys
import pandas as pd
from datetime import datetime

# ---------------- TK imports (lazy) ----------------
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------- PATHS: reliable next to EXE ----------------

def get_base_dir() -> str:
    """Return the folder that contains the running program.
    - If frozen by PyInstaller (one-file EXE): use the EXE's directory.
    - Else (running as .py): use the script's directory.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):  # this is a common PyInstaller check, but we specifically want the EXE's directory, not the temp folder
        return os.path.dirname(sys.executable)                      # the EXE's directory, which is what we want for deployment
    return os.path.dirname(os.path.abspath(__file__))               # the .py file's directory, which is what we want for development

BASE_DIR = get_base_dir()
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)                      # ensure output directory exists at startup.

# ---------------- TEAMS ----------------
TEAMS = ["Linux", "Windows", "ESXI", "Network", "Database", "Exchange"]

# ---------------- CSV header detection ----------------
def find_header_row(full_path, max_rows=50):
    header_keywords = [
        "Name","Total Downtime","Total Uptime","MTTR","MTBF","Uptime %","u_document_id",
        "server","server name","servername","server_name","host","hostname","node","machine","fqdn","instance",
    ]
    with open(full_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        for ind, line in enumerate(f):
            if ind >= max_rows:
                break
            cleaned = line.strip().lower()
            if not cleaned:
                continue
            if any(k.lower() in cleaned for k in header_keywords):
                print(f"Possible header found at line {ind}: {line.strip()}")
                return ind
    return 0

# ---------------- Column detection ----------------
def detect_server_column(df):
    cols_lower = {col.lower(): col for col in df.columns}
    possible = [
        "name","server","server name","servername","server_name","host","hostname","node","machine","fqdn","instance","u_document_id",
    ]
    for p in possible:
        if p in cols_lower:
            return cols_lower[p]
    for p in possible:
        for low, orig in cols_lower.items():
            if p in low:
                return orig
    print("No server column detected in DataFrame with columns:", list(df.columns))
    return None

# ---------------- Normalization + validation ----------------
import re
import unicodedata

_prefix_generic_re = re.compile(r'^\s*[A-Za-z0-9_\-]+\s*server\s*:\s*', flags=re.IGNORECASE)
_prefix_server_only_re = re.compile(r'^\s*server\s*:\s*', flags=re.IGNORECASE)
_ipv4_re = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')
_host_label_re = re.compile(r'^(?!-)[A-Za-z0-9_-]{1,63}(?<!-)$')
# A simple hostname validator
HOST_ALLOWED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


# ZERO-WIDTH unicode characters known to appear in your data
ZERO_WIDTH = [
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\ufeff",  # BOM
]

def remove_zero_width(s: str) -> str:
    for zw in ZERO_WIDTH:
        s = s.replace(zw, "")
    return s

# A simple heuristic to check if a string looks like a hostname or IP address.
def is_probable_hostname(s: object) -> bool:
#     if pd.isna(s):
#         return False
#     s = str(s).strip()
#     if not s:
#         return False
#     if _ipv4_re.fullmatch(s):
#         return True
#     return _host_label_re.fullmatch(s) is not None

    if pd.isna(s):
        return False

    s = remove_zero_width(str(s)).strip()

    if not s:
        return False

    if _ipv4_re.fullmatch(s):
        return True

    return HOST_ALLOWED.fullmatch(s) is not None


# Clean server names by removing common prefixes, trimming, and extracting hostnames from descriptors.
def clean_server_name(name):
#     if pd.isna(name):
#         return name
#     s = str(name).strip().strip(" '\"")
#     s = _prefix_generic_re.sub('', s)
#     s = _prefix_server_only_re.sub('', s)

#     # Fallback: descriptor:
#     if ':' in s and s.split(':', 1)[0].strip().lower() not in ("http", "https"):
#         left, right = s.split(':', 1)
#         if len(left) <= 40 and ('\n' not in right):
#             s = right.strip()

#     # UNC-like strings: \\server.domain\share -> server.domain
#     if "\\" in s:
#         s = s.strip("\\").split("\\")[-1]

#     # Keep IPv4 as-is
#     if _ipv4_re.fullmatch(s):
#         return s

#     # Reduce FQDN -> short host
#     if "." in s:
#         s = s.split(".", 1)[0]

#     return s.strip(" '\"")
    
    if pd.isna(name):
        return None

    # basic cleanup
    s = str(name).strip(" \t\r\n\"'")

    # remove invisible characters
    s = remove_zero_width(s)

    # UNC paths: \\server\share
    if "\\" in s:
        s = s.strip("\\").split("\\")[-1]

    # handle hostname@location → hostname
    if "@" in s:
        s = s.split("@", 1)[0]

    # remove prefixes like "server: xyz"
    s = _prefix_generic_re.sub("", s)
    s = _prefix_server_only_re.sub("", s)

    # handle "label: hostname" but not URLs
    if ":" in s and not s.lower().startswith(("http://", "https://")):
        left, right = s.split(":", 1)
        if len(left) <= 40:
            s = right.strip()

    # FQDN → short hostname (unless IPv4)
    if "." in s and not _ipv4_re.fullmatch(s):
        s = s.split(".", 1)[0]

    s = s.strip()
    return s or None



# Normalize the server column in a DataFrame, creating a new column with cleaned server names.
def normalize_server_column(df, server_col=None, new_col="__server_norm__"):
    if server_col is None:
        server_col = detect_server_column(df)
        if server_col is None:
            return df, None
    target = new_col or server_col
    df[target] = df[server_col].apply(clean_server_name)
    return df, target

# ---------------- Loaders for selected files ----------------

def load_selected_files(paths):
    data_frames = []
    for full_path in paths:
        file = os.path.basename(full_path)
        try:
            if file.lower().endswith(".xlsx"):
                df = pd.read_excel(full_path, engine="openpyxl")
            else:
                header_row = find_header_row(full_path)
                df = pd.read_csv(
                    full_path,
                    engine="python",
                    sep=",",
                    on_bad_lines="skip",
                    encoding="utf-8-sig",
                    dtype=str,
                    skiprows=header_row,
                    header=0,
                )
            df["__source_file__"] = file
            print(f"[OK] Loaded {file} shape={df.shape}")
            data_frames.append(df)
        except Exception as e:
            print(f"[ERROR] Failed to read {full_path}: {e}")
    return data_frames

# ---------------- Aggregation + comparison ----------------

# Aggregate server names from multiple DataFrames, normalize them, and track their sources. Returns a DataFrame with unique servers and a set of all keys for comparison.
def aggregate_servers(dfs):
    rows = []
    for df in dfs:
        df2, col = normalize_server_column(df)
        if col is None:
            continue
        src_value = str(df2["__source_file__"].iloc[0]) if "__source_file__" in df2.columns and len(df2) > 0 else "<unknown>"
        series = df2[col].dropna().astype(str).str.strip()
        series = series[series.ne("")]
        series = series[series.apply(is_probable_hostname)]
        for val in series.tolist():
            if "," in val:
                parts = [p.strip() for p in val.split(",") if p.strip()]
                for part in parts:
                    if is_probable_hostname(part):
                        rows.append((part.casefold(), part, src_value))
            else:
                rows.append((val.casefold(), val, src_value))
    if not rows:
        return pd.DataFrame(columns=["key", "server", "sources", "source_count"]), set()
    df_rows = pd.DataFrame(rows, columns=["key", "server", "source_file"])
    agg = (
        df_rows.groupby("key", as_index=False)
               .agg(server=("server", "first"), sources=("source_file", lambda s: sorted(set(map(str, s)))))
    )
    agg["source_count"] = agg["sources"].apply(len)
    agg["sources"] = agg["sources"].apply(lambda lst: "; ".join(lst))
    key_set = set(agg["key"].tolist())
    return agg, key_set

# Compare the aggregated server lists from RU and Tools, identify missing servers in each, and export the results to an Excel workbook with multiple sheets. Returns the path to the generated workbook.
def compare_and_export(ru_dfs, tools_dfs, team, output_dir=DEFAULT_OUTPUT_DIR, out_path_override=None):
    os.makedirs(output_dir, exist_ok=True)

    ru_agg, ru_keys       = aggregate_servers(ru_dfs)
    tools_agg, tools_keys = aggregate_servers(tools_dfs)

    missing_in_tools_keys = sorted(ru_keys - tools_keys)
    missing_in_ru_keys    = sorted(tools_keys - ru_keys)

    missing_in_tools = ru_agg[ru_agg["key"].isin(missing_in_tools_keys)].copy()
    missing_in_ru    = tools_agg[tools_agg["key"].isin(missing_in_ru_keys)].copy()

    summary = pd.DataFrame([
        {
            "Team": team,
            "RU_unique_servers": len(ru_keys),
            "Tools_unique_servers": len(tools_keys),
            "Missing_in_TOOLS": len(missing_in_tools_keys),
            "Missing_in_RU": len(missing_in_ru_keys),
            "Generated_At": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    ])

    for df in (ru_agg, tools_agg, missing_in_tools, missing_in_ru):
        if not df.empty:
            df.sort_values(["server", "source_count"], ascending=[True, False], inplace=True)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if out_path_override:
        xlsx_path = out_path_override
        # ensure directory exists
        os.makedirs(os.path.dirname(xlsx_path), exist_ok=True)
    else:
        xlsx_path = os.path.join(output_dir, f"{team}_compare_{ts}.xlsx")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        ru_agg[["server", "sources", "source_count", "key"]].to_excel(writer, sheet_name="RU_All", index=False)
        tools_agg[["server", "sources", "source_count", "key"]].to_excel(writer, sheet_name="Tools_All", index=False)
        missing_in_tools[["server", "sources", "source_count", "key"]].to_excel(writer, sheet_name="Missing_in_Tools", index=False)
        missing_in_ru[["server", "sources", "source_count", "key"]].to_excel(writer, sheet_name="Missing_in_RU", index=False)

        from openpyxl.utils import get_column_letter
        for sheet in ["Summary","RU_All","Tools_All","Missing_in_Tools","Missing_in_RU"]:
            ws = writer.book[sheet]
            ws.freeze_panes = "A2"
            for col_idx, col_cells in enumerate(ws.columns, start=1):
                max_len = 0
                for cell in col_cells:
                    try:
                        val = str(cell.value) if cell.value is not None else ""
                        max_len = max(max_len, len(val))
                    except Exception:
                        pass
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max(12, max_len + 2), 80)

    print(f"[OK] Wrote workbook: {xlsx_path}")
    return xlsx_path

# ---------------- GUI helpers ----------------

def ask_team_choice():
    root = tk.Tk()
    root.title("Choose Team")
    root.geometry("360x160")
    root.resizable(False, False)

    choice = tk.StringVar(value=TEAMS[0])
    done = {"ok": False, "saveas": tk.BooleanVar(value=False)}

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="Select Team:").pack(anchor=tk.W)
    cmb = ttk.Combobox(frm, values=TEAMS, textvariable=choice, state="readonly")
    cmb.current(0)
    cmb.pack(fill=tk.X, pady=6)

    chk = ttk.Checkbutton(frm, text="Let me choose where to save the report (Save As)", variable=done["saveas"])
    chk.pack(anchor=tk.W, pady=6)

    def on_ok():
        done["ok"] = True
        root.destroy()

    def on_cancel():
        done["ok"] = False
        root.destroy()

    btns = ttk.Frame(frm)
    btns.pack(fill=tk.X, pady=8)
    ttk.Button(btns, text="Cancel", command=on_cancel).pack(side=tk.RIGHT, padx=6)
    ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.RIGHT)

    root.mainloop()
    return (choice.get() if done["ok"] else None, bool(done["saveas"].get()))


def ask_files(title):
    root = tk.Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(
        title=title,
        filetypes=[
            ("Excel/CSV", "*.xlsx *.csv"),
            ("Excel", "*.xlsx"),
            ("CSV", "*.csv"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()
    return list(paths) if paths else []


def ask_save_as_suggest(team: str, default_dir: str) -> str:
    root = tk.Tk()
    root.withdraw()
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    suggested = os.path.join(default_dir, f"{team}_compare_{ts}.xlsx")
    path = filedialog.asksaveasfilename(
        title="Save report as",
        initialfile=os.path.basename(suggested),
        initialdir=os.path.dirname(suggested),
        defaultextension=".xlsx",
        filetypes=[("Excel Workbook", "*.xlsx")],
    )
    root.destroy()
    return path or ""

# ---------------- Main ----------------
if __name__ == "__main__":
    team, want_save_as = ask_team_choice()
    if not team:
        sys.exit(0)

    ru_files = ask_files(f"Select RU file(s) for {team}")
    if not ru_files:
        messagebox.showwarning("No RU files", "You did not select any RU file(s). Exiting.")
        sys.exit(0)

    tools_files = ask_files(f"Select Tools file(s) for {team}")
    if not tools_files:
        messagebox.showwarning("No Tools files", "You did not select any Tools file(s). Exiting.")
        sys.exit(0)

    ru_dfs = load_selected_files(ru_files)
    tools_dfs = load_selected_files(tools_files)

    if len(ru_dfs) == 0 and len(tools_dfs) == 0:
        messagebox.showinfo("Nothing to process", "No data could be loaded from the selected files.")
        sys.exit(0)

    out_override = None
    if want_save_as:
        # Ensure default output folder exists
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        out_override = ask_save_as_suggest(team, DEFAULT_OUTPUT_DIR)
        if not out_override:
            messagebox.showinfo("Cancelled", "Save As cancelled. No report generated.")
            sys.exit(0)

    out_path = compare_and_export(ru_dfs, tools_dfs, team, output_dir=DEFAULT_OUTPUT_DIR, out_path_override=out_override)
    messagebox.showinfo("Done", f"Report written to:\n{out_path}")

    # Open Explorer and select the file (Windows)
    try:
        import subprocess
        subprocess.run(["explorer", "/select,", out_path])
    except Exception:
        try:
            os.startfile(os.path.dirname(out_path))
        except Exception:
            pass
