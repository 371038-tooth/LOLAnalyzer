
import asyncio
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock

# Adjust path to import from src
sys.path.append(os.getcwd())

from src.utils.graph_generator import generate_report_image
from src.utils import rank_calculator

async def test_image_generation():
    print("Testing image generation...")
    headers = ["RIOT ID", "02/06", "02/05", "前日比", "7日比", "戦績"]
    data = [
        ["maguro1216", "PIII 72LP", "PIII 72LP", "±0LP", "変化なし", "3戦2勝"],
        ["kokoichi", "DII 34LP", "DII 52LP", "-18LP", "+4LP", "5戦3勝"],
        ["test_user", "S I 50LP", "S II 10LP", "+140LP", "+200LP", "10戦8勝"]
    ]
    buf = generate_report_image(headers, data, "Test Report")
    if buf:
        with open("test_report.png", "wb") as f:
            f.write(buf.getbuffer())
        print("✅ Image generated: test_report.png")
    else:
        print("❌ Image generation failed")

def test_vertical_text_logic():
    print("Testing vertical text logic (simulator)...")
    # Simulate the logic in generate_single_user_report
    history = [
        {'fetch_date': date(2026, 2, 6), 'tier': 'PLATINUM', 'rank': 'III', 'lp': 72, 'wins': 100, 'losses': 50},
        {'fetch_date': date(2026, 2, 5), 'tier': 'PLATINUM', 'rank': 'III', 'lp': 72, 'wins': 97, 'losses': 49},
        {'fetch_date': date(2026, 2, 4), 'tier': 'PLATINUM', 'rank': 'III', 'lp': 90, 'wins': 95, 'losses': 45},
    ]
    
    rid = "maguro1216#JP1"
    period_days = 7
    lines = [f"**{rid}** のレポート (過去 {period_days} 日間)", "```"]
    lines.append("日付  | ランク          | 前日比 | 戦績")
    lines.append("------|-----------------|--------|---------------")
    
    for i, h in enumerate(history):
        d_str = h['fetch_date'].strftime("%m/%d")
        r_str = rank_calculator.format_rank_display(h['tier'], h['rank'], h['lp'])
        diff_str = "-"
        record_str = "-"
        
        if i + 1 < len(history):
            prev_h = history[i+1]
            diff_str = rank_calculator.calculate_diff_text(prev_h, h, include_prefix=False)
            w = h['wins'] - prev_h['wins']
            l = h['losses'] - prev_h['losses']
            g = w + l
            if g > 0:
                rate = int((w / g) * 100)
                record_str = f"{g}戦{w}勝({rate}%)"
        
        lines.append(f"{d_str:5} | {r_str:15} | {diff_str:6} | {record_str}")
    
    lines.append("```")
    report = "\n".join(lines)
    print("✅ Vertical Text Mockup:")
    print(report)

if __name__ == "__main__":
    asyncio.run(test_image_generation())
    test_vertical_text_logic()
