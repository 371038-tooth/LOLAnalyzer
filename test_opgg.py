import asyncio
from opgg.opgg import OPGG

async def main():
    opgg = OPGG()
    try:
        # Try searching for a known user with Riot ID format
        print("Searching for Hide on bush#KR1...")
        # Note: v2 might use different search signature or not support #
        results = await opgg.search("Hide on bush#KR1", region="jp") 
        print(f"Results: {results}")
        
        if results:
            user = results[0]
            print(f"User: {user}")
            # Try to get some components to see object structure
            print(f"Name: {user.name}")
            print(f"ID: {user.id}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
