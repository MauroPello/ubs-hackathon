# UBS Data Source Manager - Frontend

This is the modern frontend for the UBS Hackathon Data Source Manager, built with **Nuxt 4** and **Nuxt UI**.

## Features
- **Premium Design**: Built with UBS-inspired aesthetics using Nuxt UI and Tailwind CSS.
- **Reactive UI**: Instant updates and smooth transitions.
- **Data Management**: Full CRUD for data sources and documentation.
- **MCP Integration**: Configure and monitor upstream MCP servers.
- **Usage Insights**: Real-time KPI dashboard.

## Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Run Development Server
Make sure the backend is running on `http://127.0.0.1:8080`.
```bash
npm run dev
```

### 3. Build for Production
```bash
npm run build
```

## Project Structure
- `app.vue`: Main layout with sidebar navigation.
- `pages/`: Application routes.
  - `index.vue`: Overview/Hero page.
  - `sources.vue`: Data source management.
  - `dashboard.vue`: Usage telemetry.
  - `mcp-servers.vue`: Upstream registry and config.
- `nuxt.config.ts`: Nuxt 4 and proxy configuration.
