import asyncio
from src.utils.opgg_client import opgg_client
from opgg.params import Region
import opgg
import sys
import importlib.metadata

async def test_lookup():
    print(f"Python version: {sys.version}")
    try:
        version = importlib.metadata.version("opgg.py")
        print(f"opgg.py version: {version}")
    except importlib.metadata.PackageNotFoundError:
        print("Could not determine opgg.py version")

    test_users = [
        ("maguro1216", "JP1", Region.JP),
    ]
    
    print("=== OPGG Integration Test ===")
    for name, tag, region in test_users:
        print(f"\nLooking up: {name}#{tag} in {region}...")
        try:
            summoner = await opgg_client.get_summoner(name, tag, region)
            
            if summoner:
                # Based on previous test, we expect a Summoner object now
                print(f"✅ User Found: {getattr(summoner, 'name', 'Unknown')}")
                print(f"Internal ID: {getattr(summoner, 'summoner_id', 'Unknown')}")
                
                print("Fetching rank info...")
                # Debugging league stats
                print(f"League stats count: {len(summoner.league_stats)}")
                for i, league in enumerate(summoner.league_stats):
                    print(f"--- League {i} ---")
                    print(f"  League Object Attrs: {dir(league)}")
                    # Try to find what looks like rank or queue
                    for attr in ['game_type', 'tier_info', 'queue_info', 'rank', 'tier', 'lp', 'division', 'queue', 'stats']:
                        if hasattr(league, attr):
                            val = getattr(league, attr)
                            print(f"  {attr} ({type(val)}): {val}")
    

                tier, rank, lp = await opgg_client.get_rank_info(summoner)
    
                print(f"\nFinal Result: {tier} {rank} ({lp} LP)")
            else:
                print(f"❌ User not found: {name}#{tag}")
        except Exception as e:
            print(f"❌ Error during lookup for {name}#{tag}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(test_lookup())
    except ImportError as e:
        print(f"ERROR: {e}")
        print("Please ensure you have installed opgg.py: pip install opgg.py>=3.1.0")
    except Exception as e:
        print(f"UNCAPTURED ERROR: {e}")
