
import asyncio
import os
import sys
from datetime import date, timedelta
import unicodedata

# Adjust path to import from src
sys.path.append(os.getcwd())

from src.utils.graph_generator import generate_report_image
from src.utils import rank_calculator

async def test_image_generation():
    print("Testing image generation with win rates...")
    headers = ["RIOT ID", "02/06", "02/05", "前日比", "7日比", "戦績"]
    data = [
        ["maguro1216", "PIII 72LP", "PIII 72LP", "Tier:変化なし LP:±0LP", "Tier:変化なし LP:±0LP", "10戦6勝(60%)"],
        ["kokoichi", "DI 8LP", "DII 52LP", "Tier DII⇒DI LP: +56LP", "Tier DII⇒DI LP: +78LP", "9戦4勝(44%)"],
    ]
    
    num_middle_dates = 2
    col_widths = [0.15] + [0.08] * num_middle_dates + [0.25, 0.25, 0.12]
    total_relative = sum(col_widths)
    col_widths = [w / total_relative for w in col_widths]
    
    buf = generate_report_image(headers, data, "Final Test Report", col_widths=col_widths)
    if buf:
        with open("test_report_final.png", "wb") as f:
            f.write(buf.getbuffer())
        print("✅ Image generated: test_report_final.png")
    else:
        print("❌ Image generation failed")

def test_vertical_text_alignment():
    print("Testing vertical text alignment check...")
    # These strings contain ambiguous width characters
    # Header: 日付(4) + ランク(6) + 前日比(6) + 戦績(4) = 20 visual width? 
    # Actually Japanese chars are 2 each.
    
    # We'll use the actual helpers from rank_calculator
    header = ["日付", "ランク", "前日比", "戦績"]
    rows = [
        ["02/06", "PIII 72LP", "Tier:変化なし LP:±0LP", "10戦6勝(60%)"],
        ["02/05", "PIII 72LP", "Tier:変化なし LP:±0LP", "5戦2勝(40%)"],
        ["02/04", "PIII 72LP", "-", "-"]
    ]
    
    col_widths = [rank_calculator.get_display_width(h) for h in header]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], rank_calculator.get_display_width(cell))

    output = []
    output.append(" | ".join([rank_calculator.pad_string(header[i], col_widths[i]) for i in range(len(header))]))
    output.append("-|-".join(["-" * w for w in col_widths]))
    for row in rows:
        output.append(" | ".join([rank_calculator.pad_string(row[i], col_widths[i]) for i in range(len(row))]))
    
    print("✅ Final Vertical Text Mockup:")
    result = "\n".join(output)
    print(result)
    
    # Verify alignment manually by checking the last | column position
    lines = result.split('\n')
    positions = [line.rfind('|') for line in lines if '-' not in line]
    print(f"Column separator positions: {positions}")
    if len(set(positions)) == 1:
        print("🎉 ALIGNMENT PERFECT!")
    else:
        print("⚠️ ALIGNMENT STILL OFF")

if __name__ == "__main__":
    asyncio.run(test_image_generation())
    test_vertical_text_alignment()
