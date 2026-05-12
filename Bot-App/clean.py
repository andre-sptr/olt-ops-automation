import re
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

# ==================== CONFIG ====================
INPUT_FILE  = "chat.txt"
OUTPUT_FILE = "chat_history.txt"
REPORT_FILE = "clean_report.txt"


# ==================== PARSER ====================

RE_TIMESTAMP = re.compile(r'^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\]\s+\S+:')
RE_TICKET_START = re.compile(r'^\s*\d+\.\s+(TSEL|OLO)\s*\|\s*(INC\d+)\s*-\s*(.*)')
RE_SEPARATOR = re.compile(r'^[—\-─═]{4,}')
RE_DAILY_HEADER = re.compile(r'^TIKET GANGGUAN NODE-B', re.IGNORECASE)


def parse_inc_blocks(filepath: str) -> dict:
    """
    Baca file dan parse menjadi dict: { inc_id: [list of (timestamp, lines)] }
    Setiap elemen list adalah satu versi broadcast tiket tersebut.
    """
    blocks = defaultdict(list)
    
    current_ts   : Optional[datetime] = None
    current_inc  : Optional[str]      = None
    current_lines: list               = []

    def flush():
        """Simpan blok yang sedang dikumpulkan"""
        if current_inc and current_lines:
            blocks[current_inc].append({
                "ts":    current_ts,
                "lines": list(current_lines)
            })

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    for raw in raw_lines:
        line = raw.rstrip("\n")

        ts_match = RE_TIMESTAMP.match(line)
        if ts_match:
            flush()
            current_inc   = None
            current_lines = []
            try:
                current_ts = datetime.fromisoformat(ts_match.group(1))
            except ValueError:
                current_ts = None
            continue 

        if RE_DAILY_HEADER.match(line.strip()):
            continue

        tk_match = RE_TICKET_START.match(line)
        if tk_match:
            flush()
            current_inc   = tk_match.group(2).strip()
            current_lines = [line]
            continue

        if current_inc is not None:
            current_lines.append(line)

    flush()

    return blocks


# ==================== DEDUPLICATOR ====================

def pick_best_version(versions: list) -> dict:
    sorted_v = sorted(versions, key=lambda v: v["ts"] or datetime.min)
    return sorted_v[-1]


# ==================== FORMATTER ====================

def clean_lines(lines: list) -> list:
    """
    Bersihkan setiap baris:
    - Hapus leading whitespace berlebihan (kecuali indentasi Timely Report)
    - Hapus trailing whitespace
    - Normalisasi separator
    - Buang baris kosong berturutan
    """
    cleaned = []
    prev_empty = False

    for line in lines:
        line = line.rstrip()

        if RE_SEPARATOR.match(line):
            line = "—" * 32
        stripped = line.lstrip()
        if stripped and not stripped[0].isdigit():
            line = stripped
        elif stripped and stripped[0].isdigit() and re.match(r'^\d+\.', stripped):
            line = "  " + stripped
        else:
            line = stripped

        if line == "":
            if prev_empty:
                continue
            prev_empty = True
        else:
            prev_empty = False

        cleaned.append(line)

    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    return cleaned


def normalize_timely_report(lines: list) -> list:
    result   = []
    in_tr    = False
    counter  = 0

    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("timely report"):
            in_tr   = True
            counter = 0
            result.append(line)
            continue

        if in_tr:
            m = re.match(r'^\s*(\d+)\.\s*(Jam\s+.+)', stripped, re.IGNORECASE)
            if m:
                counter += 1
                result.append(f"  {counter}. {m.group(2)}")
                continue
            else:
                in_tr = False

        result.append(line)

    return result


def format_block(inc_id: str, version: dict) -> str:
    ts_str = version["ts"].strftime("%Y-%m-%d %H:%M WIB") if version["ts"] else "Unknown"
    lines  = version["lines"]
    header = f"[UPDATE TERAKHIR: {ts_str}]"

    cleaned = clean_lines(lines)
    cleaned = normalize_timely_report(cleaned)

    return header + "\n" + "\n".join(cleaned)


# ==================== STATS ====================

def extract_field(lines: list, field: str) -> str:
    """Ambil nilai field dari list baris blok tiket"""
    pattern = re.compile(rf'^{re.escape(field)}\s*:\s*(.+)', re.IGNORECASE)
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            return m.group(1).strip()
    return "-"


def compute_stats(blocks_deduped: dict) -> dict:
    """Hitung statistik untuk laporan"""
    stats = {
        "total_inc"      : len(blocks_deduped),
        "status_open"    : 0,
        "status_closed"  : 0,
        "comply"         : 0,
        "not_comply"     : 0,
        "kategori"       : defaultdict(int),
        "lokasi"         : defaultdict(int),
        "penyebab"       : defaultdict(int),
    }

    for inc_id, version in blocks_deduped.items():
        lines = version["lines"]
        status    = extract_field(lines, "STATUS TIKET")
        compliance= extract_field(lines, "TTR COMPLIANCE")
        kategori  = extract_field(lines, "KATEGORI")
        lokasi    = extract_field(lines, "LOKASI")
        penyebab  = extract_field(lines, "PENYEBAB")

        if "OPEN"   in status.upper():   stats["status_open"]   += 1
        if "CLOSED" in status.upper():   stats["status_closed"] += 1
        if "NOT COMPLY" in compliance.upper(): stats["not_comply"] += 1
        elif "COMPLY" in compliance.upper():   stats["comply"]   += 1

        kat_clean = re.match(r'(\w+)', kategori)
        if kat_clean:
            stats["kategori"][kat_clean.group(1)] += 1

        lok_clean = lokasi.strip(" -")
        if lok_clean and lok_clean != "-":
            stats["lokasi"][lok_clean] += 1

        if penyebab and penyebab != "-":
            for p in penyebab.split("|"):
                p = p.strip()
                if p and p != "-":
                    stats["penyebab"][p] += 1

    return stats


def write_report(stats: dict, raw_count: int, report_path: str):
    """Tulis laporan hasil pembersihan"""
    lines = [
        "=" * 60,
        "  LAPORAN PEMBERSIHAN chat_history.txt",
        "=" * 60,
        "",
        f"Total tiket UNIK (setelah deduplikasi) : {stats['total_inc']}",
        f"Total blok broadcast (sebelum bersih)  : {raw_count}",
        f"Blok duplikat dihapus                  : {raw_count - stats['total_inc']}",
        "",
        "--- Status Tiket ---",
        f"  OPEN   : {stats['status_open']}",
        f"  CLOSED : {stats['status_closed']}",
        "",
        "--- TTR Compliance ---",
        f"  COMPLY     : {stats['comply']}",
        f"  NOT COMPLY : {stats['not_comply']}",
        "",
        "--- Breakdown Kategori ---",
    ]
    for kat, n in sorted(stats["kategori"].items()):
        lines.append(f"  {kat:<10}: {n}")

    lines += ["", "--- Breakdown Lokasi ---"]
    for lok, n in sorted(stats["lokasi"].items()):
        lines.append(f"  {lok:<10}: {n}")

    lines += ["", "--- Top Penyebab ---"]
    sorted_p = sorted(stats["penyebab"].items(), key=lambda x: x[1], reverse=True)
    for p, n in sorted_p[:10]:
        lines.append(f"  {p:<30}: {n}")

    lines += ["", "=" * 60]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))


# ==================== MAIN ====================

def main():
    input_path  = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)
    report_path = Path(REPORT_FILE)

    if not input_path.exists():
        print(f"❌ File tidak ditemukan: {INPUT_FILE}")
        print("   Letakkan script ini di folder yang sama dengan chat_history.txt")
        sys.exit(1)

    print(f"📂 Membaca: {INPUT_FILE} ({input_path.stat().st_size / 1024:.1f} KB)")

    print("🔍 Parsing blok tiket...")
    all_blocks = parse_inc_blocks(str(input_path))
    raw_total  = sum(len(v) for v in all_blocks.values())
    print(f"   Ditemukan {len(all_blocks)} INC unik dari {raw_total} total blok broadcast")
    print("🧹 Deduplikasi (simpan versi terbaru tiap INC)...")
    deduped = {}
    for inc_id, versions in all_blocks.items():
        deduped[inc_id] = pick_best_version(versions)

    sorted_incs = sorted(deduped.keys(), key=lambda x: int(re.sub(r'\D', '', x)))

    print(f"✍️  Menulis output ke: {OUTPUT_FILE}")
    output_sections = []
    for inc_id in sorted_incs:
        block_text = format_block(inc_id, deduped[inc_id])
        output_sections.append(block_text)

    final_text = "\n\n" + ("—" * 32) + "\n\n".join(output_sections) + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    print(f"📊 Menghitung statistik...")
    stats = compute_stats(deduped)
    write_report(stats, raw_total, str(report_path))

    print(f"\n✅ Selesai!")
    print(f"   Input  : {INPUT_FILE}  ({input_path.stat().st_size / 1024:.1f} KB, {raw_total} blok)")
    print(f"   Output : {OUTPUT_FILE} ({output_path.stat().st_size / 1024:.1f} KB, {len(sorted_incs)} tiket unik)")
    print(f"   Laporan: {REPORT_FILE}")
    print(f"\n👉 Upload file ini ke GCS:")
    print(f"   gsutil cp {OUTPUT_FILE} gs://<BUCKET_NAME>/chat_history.txt")


if __name__ == "__main__":
    main()