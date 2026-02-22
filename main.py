import asyncio
import feedparser
import httpx
import json
import os
import re
import time
import logging
from typing import Dict, Any, Callable, List
from dotenv import load_dotenv
from aiohttp import web

# Load environment variables
load_dotenv()

STATE_FILE = os.getenv("STATE_FILE", "state.json")
SOURCES_FILE = os.getenv("SOURCES_FILE", "sources.json")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
ERROR_LOG_FILE = os.getenv("ERROR_LOG_FILE", "error.log")

# Setup logging for system errors to a file
logging.basicConfig(
    filename=ERROR_LOG_FILE,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class EventDrivenStatusTracker:
    """
    An event-driven status page tracker designed to scale to 100+ feeds.
    It asynchronously polls feeds and dispatches events when state changes are detected.
    """
    def __init__(self, state_file: str = STATE_FILE, sources_file: str = SOURCES_FILE):
        self.state_file: str = state_file
        self.sources_file: str = sources_file
        self.state: Dict[str, str] = self._load_json(self.state_file)
        self.sources: Dict[str, str] = self._load_json(self.sources_file)
        
        # Keep track of recent messages for the web view
        self.recent_logs: List[str] = []
        
        # Event listeners that trigger when a new incident is detected
        self.event_listeners: List[Callable] = [self.handle_new_incident]

    def _load_json(self, filepath: str) -> Dict[str, str]:
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Failed to load JSON from {filepath}: {e}")
                return {}
        return {}

    def _save_state(self) -> None:
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=4)
        except IOError as e:
            logging.error(f"Error saving state to {self.state_file}: {e}")

    async def fetch_feed(self, client: httpx.AsyncClient, product: str, url: str) -> None:
        """Fetches and parses a single atom/rss feed asynchronously."""
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            content = response.text
            
            # feedparser.parse is blocking line so we run it in a thread for high concurrency
            feed = await asyncio.to_thread(feedparser.parse, content)
            
            if feed.bozo and getattr(feed.bozo_exception, 'getMessage', lambda: '')() != 'XML parsing error':
                # bozo is 1 if parser couldn't parse the feed completely
                logging.error(f"Malformed feed detected for {product} at {url}: {feed.bozo_exception}")

            if not feed or not hasattr(feed, 'entries') or not feed.entries:
                return

            latest_entry = feed.entries[0]
            # Use 'id' if available, fallback to 'link' for some RSS feeds
            entry_id = latest_entry.get("id", latest_entry.get("link"))

            # Detect if this ID is newer/different from state
            if entry_id and self.state.get(product) != entry_id:
                self.state[product] = entry_id
                self._save_state()
                
                # Dispatch to all event handlers
                for listener in self.event_listeners:
                    if asyncio.iscoroutinefunction(listener):
                        await listener(product, latest_entry)
                    else:
                        listener(product, latest_entry)

        except httpx.RequestError as exc:
            logging.error(f"An error occurred while requesting {exc.request.url!r}: {exc}")
        except httpx.HTTPStatusError as exc:
            logging.error(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}")
        except Exception as e:
            logging.error(f"Unexpected error while processing feed for {product} at {url}: {e}")

    async def handle_new_incident(self, product: str, entry: Any) -> None:
        """
        Event handler that formats and prints the notification to the console.
        Format: [Timestamp] Product: <Name> - [Incident Title] | Status: [Description].
        """
        parsed_time = entry.get('published_parsed', entry.get('updated_parsed'))
        if parsed_time:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", parsed_time)
        else:
            timestamp = entry.get('published', entry.get('updated', 'Unknown Time'))
            
        title = entry.get('title', 'Unknown Title')
        
        description = entry.get('summary', entry.get('description', 'No Description'))
        
        # Clean HTML tags from the summary to keep console output clean
        description_clean = re.sub('<[^<]+>', '', description).strip()
        # Replace newlines with spaces for single-line output
        description_clean = " ".join(description_clean.splitlines())

        output_string = f"[{timestamp}] Product: {product} - {title}\nStatus: {description_clean}"
        print(output_string)
        
        # Add to web logs so reviewers can see it on the URL
        self.recent_logs.append(output_string)
        if len(self.recent_logs) > 50:
            self.recent_logs.pop(0)

    async def fetch_feed_loop(self):
        """Main loop that continuously polls all feeds concurrently."""
        print(f"Starting tracking for {len(self.sources)} sources...")
        print("Listening for incidents... (System logs will be written to error.log)")
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=100) # optimal scaling limits
        async with httpx.AsyncClient(limits=limits) as client:
            while True:
                # Reload sources to allow dynamic adding of new providers
                self.sources = self._load_json(self.sources_file)
                
                tasks = [self.fetch_feed(client, product, url) for product, url in self.sources.items()]
                if tasks:
                    await asyncio.gather(*tasks)
                await asyncio.sleep(POLL_INTERVAL)

    async def run(self):
        """Sets up the web server and the polling loop concurrently."""
        app = web.Application()
        app.router.add_get("/", self.web_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"Web server running on port {port}")
        
        await self.fetch_feed_loop()

    async def web_handler(self, request):
        """Serves the recent logs as plain text when the URL is visited."""
        if not self.recent_logs:
            text = "No incidents detected yet.\n(The tracker is actively running in the background...)"
        else:
            text = "\n\n".join(reversed(self.recent_logs))
            
        return web.Response(text=text, content_type='text/plain')

if __name__ == "__main__":
    tracker = EventDrivenStatusTracker()
    try:
        asyncio.run(tracker.run())
    except KeyboardInterrupt:
        print("\nStopping tracker...")
