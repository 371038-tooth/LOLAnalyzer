from opgg.opgg import OPGG
from opgg.summoner import Summoner
from opgg.params import Region
import logging
import asyncio

class OPGGClient:
    def __init__(self):
        self.opgg = OPGG()

    async def get_summoner(self, name: str, tag: str, region=Region.JP) -> Summoner | None:
        """
        Fetch summoner info by name and tag.
        """
        import sys
        if sys.version_info < (3, 12):
            logging.error("CRITICAL: Python 3.12+ is required for the latest opgg.py features.")
            
        query = f"{name}#{tag}"
        try:
            # v3 version uses search() which is an alias or awaitable
            # Some versions might prefer search_async
            if hasattr(self.opgg, 'search_async'):
                summoners = await self.opgg.search_async(query, region=region)
            else:
                summoners = await self.opgg.search(query, region=region)
            
            if not summoners:
                return None
            
            result = summoners[0]
            # In v3, search returns SearchResult objects which have a .summoner attribute
            if hasattr(result, 'summoner'):
                return result.summoner
            return result


        except Exception as e:
            logging.error(f"Error searching summoner {query}: {type(e).__name__}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None


    async def get_rank_info(self, summoner: Summoner):
        """
        Fetch rank info for a summoner. 
        Returns (tier, rank, lp) for Ranked Solo.
        """
        try:
            # Refresh data
            # Refresh data only if missing
            if not getattr(summoner, 'league_stats', None):
                await summoner.update()
            
            # Check league stats
            if not hasattr(summoner, 'league_stats'):
                return "UNRANKED", "", 0

            for league in summoner.league_stats:
                raw_game_type = str(getattr(league, 'game_type', '')).upper()
                
                # Check for SOLO in the game type
                is_solo = 'SOLO' in raw_game_type

                
                if is_solo and league.tier_info:
                    # In some versions, tier/division might be in capital or not
                    tier = getattr(league.tier_info, 'tier', 'UNRANKED')
                    division = getattr(league.tier_info, 'division', '')
                    lp = getattr(league.tier_info, 'lp', 0)
                    
                    lp = getattr(league.tier_info, 'lp', 0)
                    
                    if tier:
                        return tier, division, lp



                
                # Fallback: check queue_info if it exists
                if hasattr(league, 'queue_info') and league.queue_info:
                    q_trans = str(getattr(league.queue_info, 'queue_translate', '')).lower()
                    if 'solo' in q_trans:
                        tier = league.tier_info.tier
                        division = league.tier_info.division
                        lp = league.tier_info.lp
                        return tier, division, lp


                    
            return "UNRANKED", "", 0
        except Exception as e:
            logging.error(f"Error fetching rank info for {summoner.name}: {e}")
            return "UNRANKED", "", 0


# Global instance
opgg_client = OPGGClient()
