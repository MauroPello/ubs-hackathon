# ubs-hackathon

## Goal

Design a conversational **AI assistant** that helps employees answer business questions by intelligently selecting the most relevant tables and columns from a complex underlying database schema.

## Solution

MCP server that can connect to a company's knowledge base and internal storage system (mainly BIG data DBs with many many tables (horizontally big too)). The purpose is to enable a conversational AI to answer business questions to company's employees.

To query the DBs we want to find an already made MCP server that can query efficiently all popular DBs or integrate many different MCP servers, each for a different DBMS. The former would be better as we want an agnostic solution to the specific technologies/platforms used by companies. We also want our solution to be potentially easily expandable later to other type of knowledge bases like notion, google workspace, slack, etc...

We decided for the MCP server solution because we think it's a great way to make it plug and play, have the resources to host a model yourself? perfect add MCP server support and you are ready. have an anthropic subscription? just add your mcp server to your claude!

The crucial part for which maybe we will need to do some tinkering is that we are talking about Big Data DBs here, so we could have 200+ tables to navigate through, each will have it's own detailed documentation but the issue is that we cannot load on the model's context all of the docs for all of the tables. So find a way around this, I heard about some MCP servers doing this catalog and search pattern, look into it, we might implement all of this with something like an MCP portal.
