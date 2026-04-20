// Demo business graph for a fresh Neo4j database.
// Run this after creating the database in Neo4j Browser or with cypher-shell.

CREATE CONSTRAINT region_id_unique IF NOT EXISTS
FOR (r:Region)
REQUIRE r.region_id IS UNIQUE;

CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customer_id IS UNIQUE;

CREATE CONSTRAINT product_id_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.product_id IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.order_id IS UNIQUE;

MERGE (emea:Region {region_id: 1})
  SET emea.name = "EMEA";

MERGE (amer:Region {region_id: 2})
  SET amer.name = "AMER";

MERGE (apac:Region {region_id: 3})
  SET apac.name = "APAC";

MERGE (acme:Customer {customer_id: 1})
  SET acme.name = "Acme AG",
      acme.segment = "Enterprise";

MERGE (blue:Customer {customer_id: 2})
  SET blue.name = "Blue Corp",
      blue.segment = "Mid-Market";

MERGE (zenith:Customer {customer_id: 3})
  SET zenith.name = "Zenith KK",
      zenith.segment = "Strategic";

MERGE (nordic:Customer {customer_id: 4})
  SET nordic.name = "Nordic AB",
      nordic.segment = "Enterprise";

MERGE (laptop:Product {product_id: 101})
  SET laptop.name = "Secure Laptop",
      laptop.category = "Hardware";

MERGE (vault:Product {product_id: 102})
  SET vault.name = "Vault Backup",
      vault.category = "Software";

MERGE (advisor:Product {product_id: 103})
  SET advisor.name = "Risk Advisory",
      advisor.category = "Service";

MERGE (cloud:Product {product_id: 104})
  SET cloud.name = "Cloud Workspace",
      cloud.category = "Software";

MERGE (order1:Order {order_id: 5001})
  SET order1.order_date = date("2026-01-15"),
      order1.quarter = "Q1",
      order1.revenue = 125000.0;

MERGE (order2:Order {order_id: 5002})
  SET order2.order_date = date("2026-02-02"),
      order2.quarter = "Q1",
      order2.revenue = 210500.0;

MERGE (order3:Order {order_id: 5003})
  SET order3.order_date = date("2026-02-14"),
      order3.quarter = "Q1",
      order3.revenue = 180300.0;

MERGE (order4:Order {order_id: 5004})
  SET order4.order_date = date("2026-03-01"),
      order4.quarter = "Q1",
      order4.revenue = 99000.0;

MERGE (order5:Order {order_id: 5005})
  SET order5.order_date = date("2026-04-01"),
      order5.quarter = "Q2",
      order5.revenue = 150000.0;

MERGE (acme)-[:IN_REGION]->(emea);
MERGE (blue)-[:IN_REGION]->(amer);
MERGE (zenith)-[:IN_REGION]->(apac);
MERGE (nordic)-[:IN_REGION]->(emea);

MERGE (acme)-[:PLACED]->(order1);
MERGE (blue)-[:PLACED]->(order2);
MERGE (zenith)-[:PLACED]->(order3);
MERGE (nordic)-[:PLACED]->(order4);
MERGE (acme)-[:PLACED]->(order5);

MERGE (order1)-[r1:CONTAINS_ITEM]->(laptop)
  SET r1.quantity = 20;

MERGE (order1)-[r2:CONTAINS_ITEM]->(advisor)
  SET r2.quantity = 5;

MERGE (order2)-[r3:CONTAINS_ITEM]->(vault)
  SET r3.quantity = 30;

MERGE (order3)-[r4:CONTAINS_ITEM]->(cloud)
  SET r4.quantity = 15;

MERGE (order4)-[r5:CONTAINS_ITEM]->(advisor)
  SET r5.quantity = 8;

MERGE (order5)-[r6:CONTAINS_ITEM]->(cloud)
  SET r6.quantity = 25;