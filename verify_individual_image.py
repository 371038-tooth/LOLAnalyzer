
import asyncio
import os
import sys
from datetime import date, timedelta

# Adjust path to import from src
sys.path.append(os.getcwd())

from src.utils.graph_generator import generate_report_image
from src.utils import rank_calculator

async def test_individual_image_report():
    print("Testing individual image report generation (vertical)...")
    header = ["日付", "ランク", "前日比", "戦績"]
    data = [
        ["02/07", "DI 8LP", "Tier DII⇒DI LP: +56LP", "4戦3勝(75%)"],
        ["02/06", "DII 52LP", "Tier:変化なし LP:+12LP", "6戦2勝(33%)"],
        ["02/05", "DII 40LP", "-", "-"]
    ]
    
    # Custom col_widths for individual report (vertical) as defined in scheduler.py
    col_widths = [0.12, 0.20, 0.40, 0.28]
    
    buf = generate_report_image(header, data, "Individual Report (maguro1216)", col_widths=col_widths)
    if buf:
        with open("test_individual_image.png", "wb") as f:
            f.write(buf.getbuffer())
        print("✅ Individual Image generated: test_individual_image.png")
    else:
        print("❌ Individual Image generation failed")

if __name__ == "__main__":
    asyncio.run(test_individual_image_report())
