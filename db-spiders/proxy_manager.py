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
        # List of API URLs to try in order
        self.api_templates = [
            # Old API (Expires soon)
            "https://dps.kdlapi.com/api/getdps/?secret_id=oia711htubvbiw4rgmz0&num={num}&signature=v147qflq1gdyxmwu2rde3f717hz9dpmg&sep=1",
            # New API (Backup)
            "https://dps.kdlapi.com/api/getdps/?secret_id=oban91iiljso7jppe5xk&num={num}&signature=mm7vjarupyxf6j6gk2avqpcext06jw67&sep=1"
        ]
        self.current_api_index = 0

    def fetch_proxies(self, num=5):
        """
        Fetch a batch of proxies from the API.
        Attempts to use the current working API URL. If it fails (expires), switches to the next one.
        """
        # Try APIs starting from current index
        for i in range(len(self.api_templates)):
            # Calculate actual index (circular or bounded? bounded makes more sense here, but let's just specific logic)
            # We only want to move forward if the current one fails.
            
            # If we've exhausted all APIs, stop.
            if self.current_api_index >= len(self.api_templates):
                logger.error("All Proxy APIs have failed or expired.")
                return []
                
            template = self.api_templates[self.current_api_index]
            api_url = template.format(num=num)
            
            # Retry logic for *network* errors on the SAME url
            success = False
            for attempt in range(3):
                try:
                    logger.info(f"Fetching {num} proxies (API-{self.current_api_index+1}, Attempt {attempt+1})...")
                    response = requests.get(api_url, timeout=20)
                    
                    if response.status_code != 200:
                        logger.error(f"API-{self.current_api_index+1} HTTP Error: {response.status_code}")
                        time.sleep(2)
                        continue
                        
                    text = response.text.strip()
                    
                    # API Logic Error Check
                    if '{' in text and 'msg' in text: 
                        logger.warning(f"API-{self.current_api_index+1} returned error: {text}")
                        # If error indicates expiration, STOP retrying this URL and break to outer loop to switch API
                        # Common KDL errors: "expired", "limit", "auth failed"
                        # We treat ANY logic error as a signal to try the next API
                        break 
                        
                    proxy_list = text.split('\n')
                    formatted_proxies = []
                    
                    for ip_port in proxy_list:
                        if not ip_port.strip(): continue
                        formatted_proxies.append({
                            "server": f"http://{ip_port.strip()}",
                            "username": PROXY_USERNAME,
                            "password": PROXY_PASSWORD
                        })
                    
                    if formatted_proxies:
                        logger.info(f"Successfully fetched {len(formatted_proxies)} proxies from API-{self.current_api_index+1}.")
                        return formatted_proxies
                        
                except Exception as e:
                    logger.error(f"Network error on API-{self.current_api_index+1}: {e}")
                    time.sleep(3)
            
            # If we get here, it means the current API failed (either logic error or max retries)
            # Switch to next API
            logger.warning(f"Switching from API-{self.current_api_index+1} to next available API...")
            self.current_api_index += 1
            
        return []

if __name__ == "__main__":
    # Test the manager
    pm = ProxyManager()
    proxies = pm.fetch_proxies(num=1)
    print("Test Proxy Fetch:", proxies)
