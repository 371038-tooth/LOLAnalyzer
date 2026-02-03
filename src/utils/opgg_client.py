
from opgg.v2.summoner import Summoner
from opgg.v2.params import Region
from opgg.v2.utils import Utils
import logging
import asyncio
import aiohttp
from datetime import datetime

class OPGGClient:
    def __init__(self):
        # Manually set headers and URLs to avoid OPGG() which triggers asyncio.run in some versions/components
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self._bypass_api_url = "https://lol-web-api.op.gg/api/v1.0/internal/bypass"
        self._search_api_url = f"{self._bypass_api_url}/summoners/v2/{{region}}/autocomplete?gameName={{summoner_name}}&tagline={{tagline}}"
        self._summary_api_url = f"{self._bypass_api_url}/summoners/{{region}}/{{summoner_id}}/summary"

    def _get_params(self, url):
        return {
            "base_api_url": url,
            "headers": self._headers
        }

    async def get_summoner(self, name: str, tag: str, region: Region = Region.JP):
        """Fetch summoner info by name and tag (Async)."""
        query = f"{name}#{tag}"
        # We need to construct the search URL manually for Utils._single_region_search
        url_template = self._search_api_url.format(
            region=region.value,
            summoner_name=name,
            tagline=tag
        )
        params = self._get_params(url_template)
        
        try:
            # Utils._single_region_search expects (query, region, params)
            # Its internal _search_region uses params["base_api_url"].format_map(data)
            # data = {"summoner_name": ..., "region": ..., "tagline": ...}
            # So we pass the TEMPLATE to params["base_api_url"]
            params["base_api_url"] = self._search_api_url
            results = await Utils._single_region_search(query, region, params)
            if not results:
                return None
            
            summoner_data = results[0]["summoner"]
            return Summoner(summoner_data)
        except Exception as e:
            logging.error(f"Error searching summoner {query}: {e}")
            return None

    async def get_rank_info(self, summoner: Summoner):
        """Fetch rank info for a summoner (Async)."""
        try:
            url = self._summary_api_url.format(
                region=Region.JP,
                summoner_id=summoner.summoner_id
            )
            params = self._get_params(url)
            
            profile_data = await Utils._fetch_profile(summoner.summoner_id, params)
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
