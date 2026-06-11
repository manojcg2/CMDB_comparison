# Missing Server Comparison Tool

A desktop tool (Python + Tkinter) that compares server lists from:

*   RU files
*   Tools files

and generates a multi‑sheet Excel report showing:

*   All unique servers in each source
*   Missing in Tools
*   Missing in RU
*   Summary counts per team
*   Source tracing (which file each server came from)

The tool supports CSV and Excel (.xlsx) files.

***

## Features

*   GUI with:
    *   Team selection dropdown
    *   File chooser dialogs for RU and Tools files
    *   Optional Save As dialog
*   Intelligent header detection
*   Automatic server‑name normalization (prefix cleanup, hostname/IP detection, UNC cleanup, FQDN short-name extraction)
*   Merges multiple RU and Tools files
*   Output is auto‑formatted (column widths, frozen headers)
*   Works in Python and as a PyInstaller EXE
*   Saves reports to:
    ./output/

***

## Input Requirements

RU and Tools files may be:

*   .csv
*   .xlsx

The script will:

*   Automatically identify the header row
*   Detect the server column even if named differently ("name","server","server name","servername","server\_name","host","hostname","node","machine","fqdn","instance","u\_document\_id")
*   Accept multiple RU and Tools files

***

## Output

The generated Excel workbook includes:

| Sheet              | Description                                 |
| ------------------ | ------------------------------------------- |
| Summary            | High‑level counts and timestamp             |
| RU\_All            | All normalized servers from RU with sources |
| Tools\_All         | All normalized servers from Tools           |
| Missing\_in\_Tools | Present in RU but missing in Tools          |
| Missing\_in\_RU    | Present in Tools but missing in RU          |

Output filename format:

    <team>_compare_YYYYMMDD_HHMMSS.xlsx

***

## Running the Script (Python)

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the program:

```bash
python compare_servers_gui_v2.py
```

The GUI will open and guide you through the steps.

***

## Building the EXE (PyInstaller)

To build a standalone EXE:

```bash
pyinstaller --noconsole --onefile compare_servers_gui_v2.py
```

The EXE will be created in:

    dist/compare_servers_gui_v2.exe

The tool automatically detects its folder when running as an EXE.

***

## Notes

*   The tool always creates and uses the output/ folder next to the script or EXE unless Save As is used.
*   Malformed CSV rows are handled using on\_bad\_lines="skip".
*   Server names are cleaned through prefix removal, FQDN trimming, UNC cleanup, and hostname/IP evaluation.

***

## Troubleshooting

### Excel opens the file read‑only

Close any open copy of the file and run the tool again.

### Script says it cannot detect a server column

Ensure the file contains a recognizable column name ("name","server","server name","servername","server\_name","host","hostname","node","machine","fqdn","instance","u\_document\_id").

### CSV parsing errors

Corrupted lines are skipped. Convert the file to XLSX if many rows appear invalid.

***

## Download

Download the latest EXE:
https://github.com/manojcg2/CMDB_comparison/releases/download/CMDB_comparison/compare_servers_gui_v2.exe