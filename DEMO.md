# DEMO

## Starting the server and Cloudflare tunnel

```
conda deactivate
```

```
conda activate ubs-hackathon
```

```
bash scripts/run-all.sh
```

On a new terminal:
```
cloudflared tunnel run mcp-server
```

In case you get logged out (remember to select mealfinder.site):
```
cloudflared tunnel login
```

## Actual Websites to Show

Open ChatGPT and enable Developer Mode (make sure the "UBS hackathon" app is there)

Open the dashboard available at http://localhost:3000

Open demo video and pause it at the start (to be shown in case ChatGPT takes too much time)

Ask ChatGPT the following "What was the total amount of outgoing wire transfers in April 2026 within UBS?"
