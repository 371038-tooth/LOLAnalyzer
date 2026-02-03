
from src.utils.opgg_compat import Summoner, Region, Utils, IS_V2, OPGG
import logging
import asyncio
import aiohttp
from datetime import datetime

class OPGGClient:
    def __init__(self):
        # In v3, OPGG() is likely async-friendly. In v2, we avoid it due to asyncio.run()
        if not IS_V2:
            try:
                self.opgg_instance = OPGG()
                self._headers = self.opgg_instance._headers
                # v3 might have different attributes, we'll try to map them
                self._search_api_url = getattr(self.opgg_instance, "SEARCH_API_URL", None)
                self._summary_api_url = getattr(self.opgg_instance, "SUMMARY_API_URL", None)
            except Exception:
                self.opgg_instance = None
                self._headers = {"User-Agent": "Mozilla/5.0"}
        else:
            self.opgg_instance = None
            self._headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        
        self._bypass_api_url = "https://lol-web-api.op.gg/api/v1.0/internal/bypass"
        if not getattr(self, "_search_api_url", None):
            self._search_api_url = f"{self._bypass_api_url}/summoners/v2/{{region}}/autocomplete?gameName={{summoner_name}}&tagline={{tagline}}"
        if not getattr(self, "_summary_api_url", None):
            self._summary_api_url = f"{self._bypass_api_url}/summoners/{{region}}/{{summoner_id}}/summary"

    def _get_params(self, url):
        return {
            "base_api_url": url,
            "headers": self._headers
        }

    async def get_summoner(self, name: str, tag: str, region: Region = Region.JP):
        """Fetch summoner info by name and tag (Async)."""
        query = f"{name}#{tag}"
        logging.info(f"Searching for summoner: {query} (Region: {region}, IS_V2: {IS_V2})")
        
        # v3 logic (if instance exists and is not v2)
        if not IS_V2 and self.opgg_instance:
            try:
                # Prefer search_async
                search_method = self.opgg_instance.search
                if hasattr(self.opgg_instance, 'search_async'):
                    search_method = self.opgg_instance.search_async
                    logging.info("Using search_async method")
                
                # Try Region object
                res = await search_method(query, region=region)
                
                if not res:
                    # Try region string
                    logging.info(f"v3 search returned nothing for {query} with {region}, trying with string '{region.value}'")
                    res = await search_method(query, region=region.value)
                
                if res and len(res) > 0:
                    logging.info(f"v3 search found {len(res)} results for {query}")
                    # In v3 SearchResult has .summoner
                    return res[0].summoner if hasattr(res[0], 'summoner') else res[0]
                else:
                    logging.info(f"v3 search returned no results for {query}")
            except Exception as e:
                logging.error(f"v3 search error for {query}: {e}")

        # v2 or Fallback logic
        url_template = self._search_api_url.format(
            region=region.value,
            summoner_name=name,
            tagline=tag
        )
        params = self._get_params(url_template)
        logging.info(f"Using fallback search for {query} (URL: {url_template})")
        
        try:
            if Utils and hasattr(Utils, '_single_region_search'):
                # We need the original template for format_map inside Utils
                params["base_api_url"] = self._search_api_url
                results = await Utils._single_region_search(query, region, params)
                if results:
                    logging.info(f"Fallback search found {len(results)} results for {query}")
                    summoner_data = results[0]["summoner"]
                    return Summoner(summoner_data)
                else:
                    logging.info(f"Fallback search returned no results for {query}")
        except Exception as e:
            logging.error(f"Fallback search error for {query}: {e}")
            
        return None

    async def get_rank_info(self, summoner: Summoner):
        """Fetch rank info for a summoner (Async)."""
        # v3 logic
        if not IS_V2 and self.opgg_instance:
            try:
                # In v3, maybe summoner.profile() or opgg.profile(summoner)
                # But typically summoner objects have lazy loading or explicit update
                # Let's try the summary API directly as fallback if update() is sync
                pass
            except Exception:
                pass

        # Fallback / v2 manual logic
        try:
            url = self._summary_api_url.format(
                region=Region.JP,
                summoner_id=summoner.summoner_id
            )
            params = self._get_params(url)
            
            if Utils and hasattr(Utils, '_fetch_profile'):
                profile_data = await Utils._fetch_profile(summoner.summoner_id, params)
            else:
                # Direct aiohttp fetch if Utils is missing (v3 case where we don't have OPGG methods yet)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self._headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            profile_data = data.get('data', {})
                        else:
                            profile_data = None

            if not profile_data:
                return "UNRANKED", "", 0, 0, 0
                
            stats = profile_data.get('league_stats', [])
            for stat in stats:
                if stat.get('queue_info', {}).get('game_type') == 'SOLORANKED':
                    tier_info = stat.get('tier_info', {})
                    tier = tier_info.get('tier', 'UNRANKED')
                    division = tier_info.get('division', '')
                    lp = tier_info.get('lp', 0)
                    wins = stat.get('win', 0)
                    losses = stat.get('lose', 0)
                    return tier, self.division_to_roman(division), lp, wins, losses
            
            return "UNRANKED", "", 0, 0, 0
        except Exception as e:
            logging.error(f"Error fetching rank info: {e}")
            return "UNRANKED", "", 0, 0, 0

    async def get_win_loss(self, summoner: Summoner):
        _, _, _, w, l = await self.get_rank_info(summoner)
        return w, l

    def division_to_roman(self, division):
        if isinstance(division, int):
            mapping = {1: "I", 2: "II", 3: "III", 4: "IV"}
            return mapping.get(division, str(division))
        div_str = str(division).upper()
        if div_str == "1": return "I"
        if div_str == "2": return "II"
        if div_str == "3": return "III"
        if div_str == "4": return "IV"
        return div_str

    async def get_tier_history(self, summoner_id: str, region: Region):
        url = f"https://lol-web-api.op.gg/api/v1.0/internal/bypass/summoners/{region.value}/{summoner_id}/tier-history"
        headers = self._headers
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logging.error(f"Failed to fetch tier history: HTTP {response.status}")
                        return []
                    data = await response.json()
                    history_list = data.get('data', [])
                    results = []
                    for entry in history_list:
                        tier_info = entry.get('tier_info', {})
                        updated_at_str = entry.get('created_at')
                        if not tier_info or not updated_at_str: continue
                        try:
                            updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                        except Exception: continue
                        results.append({
                            'tier': tier_info.get('tier', 'UNRANKED'),
                            'rank': self.division_to_roman(tier_info.get('division', '')),
                            'lp': tier_info.get('lp', 0),
                            'wins': 0,
                            'losses': 0,
                            'updated_at': updated_at
                        })
                    return results
        except Exception as e:
            logging.error(f"Error in get_tier_history: {e}")
            return []

# Global instance
opgg_client = OPGGClient()
