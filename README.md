# OpenAI Status Tracker

A lightweight, event-driven application that automatically tracks service updates from the OpenAI Status Page and 100+ other status pages efficiently.

## Core Features
- **Event-Based Architecture**: Avoids unnecessary polling logic by processing the Atom/RSS feeds asynchronously and keeping track of the latest incident ID.
- **Scalable**: Uses `asyncio` and `httpx` with connection pooling to handle fetching 100+ endpoints concurrently without blocking.
- **Dynamic Configuration**: Modify `sources.json` to add/remove status pages on the fly. The application dynamically reloads this file at the start of each polling cycle.
- **Robust Iteration**: Includes standard error handling and localized fallback parsing logic for malformed XML or broken connections so the main loop never crashes. System logs are pushed to an `error.log` while incident outputs are kept clean on stdout.

## Getting Started Locally

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Make a copy of `.env.example` as `.env`:
   ```bash
   cp .env.example .env
   ```
3. Run the script:
   ```bash
   python main.py
   ```

## Configuration

* **`sources.json`**: An object containing key-value mappings of Providers -> Atom/RSS URLs. Example:
   ```json
   {
       "OpenAI": "https://status.openai.com/history.atom",
       "GitHub": "https://www.githubstatus.com/history.atom",
       "Tailscale": "https://status.tailscale.com/history.atom"
   }
   ```
* **`.env`**: Customize path names and `POLL_INTERVAL` (in seconds).

## Running via Docker

Build the container image:
```bash
docker build -t status-tracker .
```

Run the container in detached mode (pass `-v` to persist the state and logs):
```bash
docker run -d --name status-tracker \
    -v $(pwd)/state.json:/app/state.json \
    -v $(pwd)/sources.json:/app/sources.json \
    -v $(pwd)/error.log:/app/error.log \
    status-tracker
```
