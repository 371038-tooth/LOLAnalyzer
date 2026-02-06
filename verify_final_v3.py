
import asyncio
import os
import sys
from datetime import date, timedelta
from tabulate import tabulate

# Adjust path to import from src
sys.path.append(os.getcwd())

from src.utils.graph_generator import generate_report_image
from src.utils import rank_calculator

async def test_image_generation():
    print("Testing final image generation with win rates...")
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
        with open("test_report_final_v2.png", "wb") as f:
            f.write(buf.getbuffer())
        print("✅ Image generated: test_report_final_v2.png")
    else:
        print("❌ Image generation failed")

def test_vertical_text_alignment_with_tabulate():
    print("Testing vertical text alignment with tabulate...")
    header = ["日付", "ランク", "前日比", "戦績"]
    rows = [
        ["02/06", "PIII 72LP", "Tier:変化なし LP:±0LP", "10戦6勝(60%)"],
        ["02/05", "PIII 72LP", "Tier:変化なし LP:±0LP", "5戦2勝(40%)"],
        ["02/04", "PIII 72LP", "-", "-"]
    ]
    
    table_text = tabulate(rows, headers=header, tablefmt="presto")
    
    print("✅ Final Vertical Text Mockup (Tabulate):")
    print(table_text)
    
    # Check alignment manually
    lines = table_text.split('\n')
    # Presto format uses pipes or just spaces. Let's see.
    for line in lines:
        print(f"'{line}'")

if __name__ == "__main__":
    asyncio.run(test_image_generation())
    test_vertical_text_alignment_with_tabulate()
