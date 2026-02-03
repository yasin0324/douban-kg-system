# -*- coding: utf-8 -*-
import requests
import time
import threading
import logging

# Configuration for Kuaidaili (KDL)
# API Url template - num will be replaced
BASE_API_URL = "https://dps.kdlapi.com/api/getdps/?secret_id=oia711htubvbiw4rgmz0&num={num}&signature=v147qflq1gdyxmwu2rde3f717hz9dpmg&sep=1"
PROXY_USERNAME = "d3051442632"
PROXY_PASSWORD = "r2432tcw"

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProxyManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_proxies = []

    def fetch_proxies(self, num=5):
        """
        Fetch a batch of proxies from the API.
        
        Args:
            num: Number of proxies to fetch.
            
        Returns:
            List of proxy dicts formatted for Playwright:
            [{'server': 'http://ip:port', 'username': '...', 'password': '...'}]
        """
        api_url = BASE_API_URL.format(num=num)
        try:
            logger.info(f"Fetching {num} new proxies from KDL...")
            response = requests.get(api_url, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"API Error: HTTP {response.status_code}")
                return []
                
            text = response.text.strip()
            
            # Check for API errors (KDL often returns errors in plain text)
            if '{' in text and 'msg' in text: # Simple check for JSON error
                logger.error(f"API returned error message: {text}")
                return []
                
            proxy_list = text.split('\n')
            formatted_proxies = []
            
            # Use a Set to deduplicate IPs if API returns duplicates (rare)
            # but more importantly, we assume these are NEW IPs.
            
            for ip_port in proxy_list:
                if not ip_port.strip():
                    continue
                
                # Format for Playwright
                # "server": "http://ip:port"
                # "username": ...
                # "password": ...
                
                # KDL returns just "ip:port" usually
                proxy_config = {
                    "server": f"http://{ip_port.strip()}",
                    "username": PROXY_USERNAME,
                    "password": PROXY_PASSWORD
                }
                formatted_proxies.append(proxy_config)
            
            logger.info(f"Successfully fetched {len(formatted_proxies)} proxies.")
            return formatted_proxies
            
        except Exception as e:
            logger.error(f"Failed to fetch proxies: {e}")
            return []

if __name__ == "__main__":
    # Test the manager
    pm = ProxyManager()
    proxies = pm.fetch_proxies(num=1)
    print("Test Proxy Fetch:", proxies)
