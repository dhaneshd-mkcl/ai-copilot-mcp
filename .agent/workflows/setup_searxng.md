---
description: how to setup and configure a local SearXNG search engine for Antigravity
---

# Setup SearXNG Workflow

1. Ensure Docker is installed and running on your system.
2. Create or navigate to a directory for search infrastructure.
3. Run the SearXNG Docker container:
   ```bash
   docker run -d -p 8080:8080 --name searxng searxng/searxng
   ```
4. To enable the JSON API (required for Antigravity):
   - Locate the configuration file (usually inside the container or mounted volume).
   - Ensure the `formats` list includes `json`.
   - Restart the container: `docker restart searxng`.
5. Verify the API is working:
   ```bash
   curl "http://localhost:8080/search?q=test&format=json"
   ```
6. Update the `.env` file in the backend directory:
   ```env
   SEARXNG_BASE_URL=http://localhost:8080
   ```
7. Restart the Antigravity backend.
