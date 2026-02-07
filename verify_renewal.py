
import asyncio
import os
import sys
import logging

# Adjust path to import from src
sys.path.append(os.getcwd())

from src.utils.opgg_client import opgg_client

async def verify_renewal():
    logging.basicConfig(level=logging.INFO)
    print("Testing OP.GG Renewal for a known user...")
    
    # Use a known user for testing
    name, tag = "maguro1216", "JP1"
    
    summoner = await opgg_client.get_summoner(name, tag)
    if not summoner:
        print(f"❌ Could not find summoner {name}#{tag}")
        return

    print(f"Found summoner: {summoner.game_name}#{summoner.tagline} (ID: {summoner.summoner_id})")
    
    success = await opgg_client.renew_summoner(summoner)
    if success:
        print("✅ Renewal request successful (200/201/202)")
    else:
        print("❌ Renewal request failed")

if __name__ == "__main__":
    asyncio.run(verify_renewal())
