import requests
import logging

logger = logging.getLogger(__name__)

class ProxyClient:
    def __init__(self, timeout=10):
        self.timeout = timeout
        # Using a Session enables connection pooling for better performance
        self.session = requests.Session()

    def request(self, service_url, path, method="GET", params=None, data=None):
        url = f"{service_url}{path}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=self.timeout
            )
            # Return JSON if possible, otherwise raw text
            try:
                return response.json(), response.status_code
            except ValueError:
                return {"data": response.text}, response.status_code

        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error to {service_url}")
            return {"error": f"Service {service_url} unavailable"}, 503
        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to {service_url}")
            return {"error": "Service timeout"}, 504
        except Exception as e:
            logger.error(f"Proxy error: {str(e)}")
            return {"error": "Internal gateway error"}, 500