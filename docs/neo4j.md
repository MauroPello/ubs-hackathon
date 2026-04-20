# Neo4j Setup

This walkthrough shows how to start a fresh local Neo4j database, run the Neo4j MCP server, and load a small demo graph.

## 1) Create and run Neo4j

The simplest local setup is Docker. Replace the password before using this in a shared environment.

```bash
docker volume create ubs-neo4j-data

docker run --name ubs-neo4j \
  --detach \
  --publish 7474:7474 \
  --publish 7687:7687 \
  --env NEO4J_AUTH=neo4j/ChangeMe123! \
  --env NEO4J_PLUGINS='["apoc"]' \
  --volume ubs-neo4j-data:/data \
  neo4j:5.26.1
```

Wait until the container reports that Neo4j is ready, then open:

- Neo4j Browser: http://localhost:7474
- Bolt endpoint: bolt://localhost:7687

If you prefer Neo4j Desktop or a managed Aura instance, create the database there and make sure APOC is enabled.

## 2) Load the demo data

The demo graph lives in [data/neo4j_demo.cypher](data/neo4j_demo.cypher). You can load it with `cypher-shell`:

```bash
cypher-shell \
  -a bolt://localhost:7687 \
  --username neo4j \
  --password 'ChangeMe123!' \
  --file data/neo4j_demo.cypher
```

If you do not have `cypher-shell` installed, open Neo4j Browser and paste the file contents into a new query tab.

## 3) Run the Neo4j MCP server

The Neo4j MCP server used by this project is `mcp-neo4j-cypher`.

### Local stdio mode

This is the easiest way to connect the server to an MCP client such as VS Code or Claude Desktop.

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=ChangeMe123!
export NEO4J_DATABASE=neo4j

uvx mcp-neo4j-cypher@0.6.0 --transport stdio
```

### Local HTTP mode

Use HTTP if you want the MCP server reachable over the network or through a browser-based MCP client.

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=ChangeMe123!
export NEO4J_DATABASE=neo4j

uvx mcp-neo4j-cypher@0.6.0 --transport http --server-host 127.0.0.1 --server-port 8000 --server-path /mcp-neo4j/
```

The upstream Neo4j server exposes tools such as `read_neo4j_cypher` and `get_neo4j_schema`. If you are wiring it into this repo's delegated graph adapter, map its query tool to `execute_cypher` in your config.

## 4) Optional check

Open the Neo4j Browser and run:

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.name AS customer, count(o) AS orders, sum(o.revenue) AS revenue
ORDER BY revenue DESC;
```

You should see a small sales graph with customers, regions, products, and orders.