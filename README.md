# Oxylabs Web API for Hermes Agent

A [Hermes Agent](https://hermes-agent.nousresearch.com/) plugin that adds the [Oxylabs Web API](https://oxylabs.io/products/web-api) as a provider for Hermes's built-in `web_search` and `web_extract` tools.

- **web_search**: Google results with titles, URLs and a short outline of each page. Set a country to see results as users in that country do.
- **web_extract**: any page as Markdown, including JavaScript-heavy pages (turn on JavaScript rendering) and pages that block plain HTTP clients.

The agent keeps using the tools Hermes already has; you choose Oxylabs as the backend.

## Requirements

- Hermes Agent 0.23.1 or later.
- An Oxylabs Web API key. Get one in the [Oxylabs dashboard](https://dashboard.oxylabs.io/).

## Set up

1. Install and enable the plugin:

   ```bash
   hermes plugins install oxylabs-web-api --enable
   ```

   The plugin is in the Hermes plugin catalog, so Hermes installs the reviewed version. It asks before installing the plugin's one dependency (`httpx`, which Hermes already uses). In scripts, add `--yes-deps`.

   To install the latest commit instead, run `hermes plugins install oxylabs/hermes-oxylabs-web-api --enable`. Hermes warns that this source is not from its reviewed catalog.

2. Add your key. The install asks for it; paste it there, or skip and add it later. To add it later, run `hermes tools`, open **Web Search & Extract**, select **Oxylabs Web API** and paste the key. Or add it to your profile's `.env` file (`~/.hermes/.env` for the default profile):

   ```bash
   OXYLABS_WEB_API_KEY=your-web-api-key
   ```

3. Select Oxylabs for search, extraction, or both:

   ```bash
   hermes config set web.search_backend oxylabs
   hermes config set web.extract_backend oxylabs
   ```

Start a new session after these steps.

## Settings

Both are optional:

```bash
hermes config set plugins.entries.oxylabs-web-api.settings.location US
hermes config set plugins.entries.oxylabs-web-api.settings.render_js true
```

| Setting | Default | What it does |
|---|---|---|
| `location` | none | Two-letter country code for searches, such as `US` or `DE`. |
| `render_js` | `false` | Load pages in a browser before extracting them. Slower and uses more credits; turn it on if pages come back nearly empty. |

The Hermes desktop app shows the same settings on the plugin's page under **Settings → Plugins**.

Slow pages are queued on the asynchronous Web API and polled, and each page gets up to 110 seconds, just inside Hermes's 120-second extract timeout.

## Your data

- The plugin sends your search queries and the URLs you ask Hermes to read to `https://webapi.oxylabs.io`, together with your API key. It contacts no other service. Requests are billed to your Oxylabs account.
- Oxylabs runs each search and loads each page, so the sites you read receive Oxylabs's request. Before a page is fetched, Hermes checks the address on your machine and blocks private and internal ones.
- Requests carry an `x-oxylabs-sdk: oxylabs-web-api-hermes/<version>` header so Oxylabs can count usage per integration. It holds the plugin and Python versions only.
- The plugin reads the key through Hermes and never includes it in results or error messages. It collects no telemetry, runs no shell commands or background processes, and reads none of your files.

## Update or remove

```bash
hermes plugins update oxylabs-web-api
hermes plugins remove oxylabs-web-api
hermes config unset web.search_backend
hermes config unset web.extract_backend
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `OXYLABS_WEB_API_KEY is not set` | Add the key as in step 2, then start a new session. |
| `rejected the API key (401)` | The key is wrong or revoked. Check it in the Oxylabs dashboard. |
| `quota is used up (429 QUOTA_EXCEEDED)` | Top up the plan in the Oxylabs dashboard. |
| `web_search` uses another provider | Run the `hermes config set` commands from step 3. Check `hermes plugins list` shows `oxylabs-web-api` as enabled. |
| A page comes back nearly empty | Turn on `render_js`. |

## Install from PyPI

If you run Hermes from a Python environment you manage yourself, install the package into the interpreter that runs Hermes and enable it:

```bash
uv pip install --python /path/to/hermes/python hermes-oxylabs-web-api
hermes plugins enable oxylabs-web-api
```

`hermes plugins update` and `remove` don't manage a PyPI install; upgrade or uninstall it with the same tool.

## Development

```bash
uv sync --dev
uv run ruff check . && uv run ruff format --check .
uv run pytest                                       # unit tests
OXYLABS_WEB_API_KEY=... uv run pytest -m live       # calls the real API
hermes plugins validate .                           # the checks the Hermes catalog runs
```

The `Hermes end-to-end` workflow installs the latest stable Hermes, runs the catalog checks, installs the plugin from this repository (or by its catalog name, when started by hand with `source: catalog`) and calls `web_search` and `web_extract` against the live API.

Releases: bump the version in `pyproject.toml`, both `plugin.yaml` files and `src/hermes_oxylabs_web_api/__init__.py`, add a `CHANGELOG.md` entry, then push a `v<version>` tag. The `Publish` workflow publishes to PyPI with trusted publishing.

## License

MIT
