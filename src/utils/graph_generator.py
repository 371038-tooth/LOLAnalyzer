
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, date, timedelta
import io
import os
from typing import List, Dict, Any

# Rank Mapping
TIER_ORDER = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", 
    "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"
]

DIV_MAP = {"I": 3, "II": 2, "III": 1, "IV": 0}

def rank_to_numeric(tier: str, division: str, lp: int) -> int:
    """Convert Tier/Division/LP to a single numeric value for graphing."""
    tier = tier.upper()
    if tier not in TIER_ORDER:
        return 0
    
    tier_val = TIER_ORDER.index(tier) * 400
    
    # Apex tiers don't have divisions
    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        # We give Master 2800, GM 3200, Challenger 3600 base? 
        # Or just use the index.
        # Let's say Master starts at 2800.
        return tier_val + lp
    
    div_val = DIV_MAP.get(division, 0) * 100
    return tier_val + div_val + lp

def numeric_to_rank(val: int) -> str:
    """Convert numeric value back to a human-readable rank label (approximate)."""
    tier_idx = val // 400
    if tier_idx >= len(TIER_ORDER):
        tier_idx = len(TIER_ORDER) - 1
    
    tier = TIER_ORDER[tier_idx]
    
    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        lp = val % 400 # This is a bit arbitrary for Apex
        return f"{tier}"
    
    rem = val % 400
    div_idx = rem // 100
    lp = rem % 100
    
    div_names = ["IV", "III", "II", "I"]
    div = div_names[div_idx] if div_idx < 4 else "I"
    
    return f"{tier} {div}"

def generate_rank_graph(rows: List[Dict[str, Any]], period_type: str, riot_id: str) -> io.BytesIO:
    """
    Generate a rank history graph.
    rows: List of dicts with 'fetch_date', 'tier', 'rank', 'lp'
    period_type: 'daily', 'weekly', 'monthly'
    """
    if not rows:
        return None

    # Filter by year logic: If spanning years, start from Jan 1st of the current year
    # Actually, the user says: "年を跨いだ場合は、必ず1月からのブラフを出すようにします。"
    # I'll check if the earliest date year is different from the latest date year.
    latest_date = max(r['fetch_date'] for r in rows)
    earliest_date = min(r['fetch_date'] for r in rows)
    
    if earliest_date.year < latest_date.year:
        # Start from Jan 1st of the latest year
        start_filter = date(latest_date.year, 1, 1)
        rows = [r for r in rows if r['fetch_date'] >= start_filter]
        if not rows: # If no data in the newest year, just show the last available?
            # User requirement says "must show from Jan", so maybe empty is fine or show the last year entirely.
            # But usually it means "don't show the previous year part".
            pass

    dates = [r['fetch_date'] for r in rows]
    values = [rank_to_numeric(r['tier'], r['rank'], r['lp']) for r in rows]

    # Plotting
    plt.figure(figsize=(10, 6))
    plt.plot(dates, values, marker='o', linestyle='-', color='#1abc9c', linewidth=2, markersize=6)
    
    # Title and Labels
    # Use Riot ID name part
    name = riot_id.split('#')[0]
    plt.title(f"Rank History: {name} ({period_type})", fontsize=17, color='white', pad=25, weight='bold')
    plt.xlabel("Date", fontsize=14, color='white', labelpad=10)
    plt.ylabel("Rank", fontsize=14, color='white', labelpad=10)

    # Formatting Axes
    ax = plt.gca()
    ax.set_facecolor('#2c3e50')
    plt.gcf().set_facecolor('#34495e')
    
    # Tick colors and sizes
    ax.tick_params(colors='white', labelsize=11)
    for spine in ax.spines.values():
        spine.set_color('#7f8c8d')

    # Date Formatting on X-axis
    if period_type == 'daily':
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator())
    elif period_type == 'weekly':
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    elif period_type == 'monthly':
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator())

    plt.xticks(rotation=45, fontsize=11)

    # Determine Y-axis range and labels
    if values:
        min_v = min(values)
        max_v = max(values)
        
        # Tight range: start of the lowest rank to the end of the highest rank in data
        y_min = (min_v // 100) * 100
        y_max = ((max_v // 100) + 1) * 100
        
        ax.set_ylim(y_min, y_max)
        
        # Set ticks at every 100 LP (Division boundary)
        y_ticks = list(range(int(y_min), int(y_max) + 1, 100))
        
        # Custom labels: repeat the lower rank name at the top boundary if it's the same rank
        y_labels = []
        for i, t in enumerate(y_ticks):
            if i == len(y_ticks) - 1 and len(y_ticks) > 1:
                # For the very top tick, show the label for the rank just below it
                # effectively labeling the "range" of that rank.
                y_labels.append(numeric_to_rank(y_ticks[i-1]))
            else:
                y_labels.append(numeric_to_rank(t))
        
        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_labels, fontsize=11)

    # Add LP annotations
    for i, r in enumerate(rows):
        val = values[i]
        lp = r['lp']
        d = dates[i]
        ax.annotate(f"{lp}LP", (d, val), 
                    textcoords="offset points", 
                    xytext=(0, 12), 
                    ha='center', 
                    fontsize=12, 
                    color='white',
                    weight='bold')

    # Add Grid
    plt.grid(True, linestyle='--', alpha=0.2, color='#95a5a6')

    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', transparent=False, dpi=100)
    buf.seek(0)
    plt.close()
    
    return buf
