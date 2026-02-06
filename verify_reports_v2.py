
import asyncio
import os
import sys
from datetime import date, timedelta
import unicodedata

# Adjust path to import from src
sys.path.append(os.getcwd())

from src.utils.graph_generator import generate_report_image
from src.utils import rank_calculator

def get_display_width(s):
    width = 0
    for char in str(s):
        eaw = unicodedata.east_asian_width(char)
        if eaw in ('W', 'F', 'A'):
            width += 2
        else:
            width += 1
    return width

def pad_string(s, width):
    s_str = str(s)
    current_w = get_display_width(s_str)
    return s_str + (" " * max(0, width - current_w))

async def test_image_generation():
    print("Testing refined image generation...")
    headers = ["RIOT ID", "02/06", "02/05", "前日比", "7日比", "戦績"]
    data = [
        ["maguro1216", "PIII 72LP", "PIII 72LP", "Tier:変化なし LP:±0LP", "Tier:変化なし LP:±0LP", "-"],
        ["kokoichi", "DI 8LP", "DII 52LP", "Tier DII⇒DI LP: +56LP", "Tier DII⇒DI LP: +78LP", "9戦4勝"],
        ["ikebon", "SIV 99LP", "-", "-", "-", "-"]
    ]
    
    # Calculate colWidths in the same way as scheduler.py
    num_middle_dates = 2
    col_widths = [0.15] + [0.08] * num_middle_dates + [0.25, 0.25, 0.1]
    total_relative = sum(col_widths)
    col_widths = [w / total_relative for w in col_widths]
    
    buf = generate_report_image(headers, data, "Refined Test Report", col_widths=col_widths)
    if buf:
        with open("test_report_refined.png", "wb") as f:
            f.write(buf.getbuffer())
        print("✅ Image generated: test_report_refined.png")
    else:
        print("❌ Image generation failed")

def test_vertical_text_logic():
    print("Testing refined vertical text logic (simulator)...")
    history = [
        {'fetch_date': date(2026, 2, 6), 'tier': 'PLATINUM', 'rank': 'III', 'lp': 72, 'wins': 100, 'losses': 50},
        {'fetch_date': date(2026, 2, 5), 'tier': 'PLATINUM', 'rank': 'III', 'lp': 72, 'wins': 100, 'losses': 50},
        {'fetch_date': date(2026, 2, 4), 'tier': 'PLATINUM', 'rank': 'III', 'lp': 72, 'wins': 100, 'losses': 50},
    ]
    
    rid = "maguro1216#JP1"
    rows = []
    # Simplified simulation of the loop in scheduler.py
    for i, h in enumerate(history):
        d_str = h['fetch_date'].strftime("%m/%d")
        r_str = f"PIII 72LP"
        diff_str = "Tier:変化なし LP:±0LP" if i < 2 else "-"
        record_str = "-"
        rows.append([d_str, r_str, diff_str, record_str])

    header = ["日付", "ランク", "前日比", "戦績"]
    col_widths = [get_display_width(h) for h in header]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], get_display_width(cell))

    lines = [" | ".join([pad_string(header[i], col_widths[i]) for i in range(len(header))])]
    lines.append("-|-".join(["-" * w for w in col_widths]))
    for row in rows:
        lines.append(" | ".join([pad_string(row[i], col_widths[i]) for i in range(len(row))]))
    
    print("✅ Refined Vertical Text Mockup:")
    print("\n".join(lines))

if __name__ == "__main__":
    asyncio.run(test_image_generation())
    test_vertical_text_logic()
