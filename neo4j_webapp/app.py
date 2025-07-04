import re
from flask import Flask, jsonify, render_template, request, Response
from neo4j import GraphDatabase
import json
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Flask app setup
app = Flask(__name__)

# Neo4j connection setup
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
print(f"Connecting to Neo4j at {NEO4J_URI} with user {NEO4J_USER}")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Predefined queries for the web interface
QUERIES = {
    "former_employees": {
        "description": "Find former employees of a company",
        "cypher": """
            MATCH (p:Person)-[r:formerly_employed]-(c:Company)
            WHERE c.id = $identifier OR c.name = $identifier
            RETURN p.name AS Name, p.title AS Title, r.notes AS Notes
        """,
        "params": ["identifier"],
    },
    "former_gov_employees": {
        "description": "Find former employees of a government body",
        "cypher": """
            MATCH (p:Person)-[r:formerly_employed]-(g:`Government Body`)
            WHERE g.id = $identifier OR g.name = $identifier
            RETURN p.name AS Name, p.title AS Title, r.notes AS Notes
        """,
        "params": ["identifier"],
    },
    "people_who_know": {
        "description": "Return all people who know a person",
        "cypher": """
            MATCH (p:Person)
            WHERE p.id = $identifier OR p.name = $identifier
            MATCH (p)-[r:knows|works_with]-(other:Person)
            RETURN other.name AS Name, other.title AS Title, r.notes AS Notes 
        """,
        "params": ["identifier"],
    },
    "Gov_contracts": {
        "description": "Return all Companies that work with a Government Body",
        "cypher": """
            MATCH (g:`Government Body`)
            WHERE g.id = $identifier OR g.name = $identifier
            MATCH (g)-[r:contracts]-(c:Company)
            RETURN c.name AS Company, r.notes AS Notes
        """,
        "params": ["identifier"],
    },
    # Add more queries here as needed
}

@app.route('/')
def index():
    # Render the main index page with available queries
    return render_template('index.html', queries=QUERIES)

@app.route('/query', methods=['POST'])
def run_query():
    # Run a selected query from the web interface
    query_id = request.form.get('query_id')
    if not query_id or query_id not in QUERIES:
        return "Invalid query selected", 400

    query_info = QUERIES[query_id]
    params = {}

    # Determine which identifier to use based on the query type
    identifier = None
    if "person" in query_id:
        identifier = request.form.get("person_identifier")
    elif "company" in query_id:
        identifier = request.form.get("company_identifier")
    elif "gov" in query_id or "government" in query_id:
        # Try both, fallback to person/company if not present
        identifier = (
            request.form.get("company_identifier")
            or request.form.get("person_identifier")
            or request.form.get("government_identifier")
        )
    else:
        # Fallback: try both
        identifier = request.form.get("person_identifier") or request.form.get("company_identifier")

    # For queries that require 'identifier'
    if "identifier" in query_info["params"]:
        if not identifier:
            return "Missing identifier parameter.", 400
        params["identifier"] = identifier

    # If you add queries with other params, handle them here

    with driver.session() as session:
        try:
            result = session.run(query_info["cypher"], **params)
            columns = result.keys()
            results = [dict(record) for record in result]
        except Exception as e:
            # Render error if query fails
            return render_template("results.html", title="Query Error", results=[[str(e)]], columns=["Error"])

    return render_template("results.html", title=query_info["description"], results=results, columns=columns)

@app.route("/schema-data")
def schema_data():
    # Return a static schema graph (node types and relationship types)
    nodes = [
        {"id": "Person", "label": "Person", "group": "Person"},
        {"id": "Company", "label": "Company", "group": "Company"},
        {"id": "GovernmentBody", "label": "Government Body", "group": "GovernmentBody"},
    ]
    edges = [
        {"from": "Person", "to": "Person", "label": "knows"},
        {"from": "Person", "to": "Person", "label": "works_with"},
        {"from": "Person", "to": "Company", "label": "formerly_employed"},
        {"from": "Person", "to": "Company", "label": "employed"},
        {"from": "Company", "to": "Company", "label": "contracts"},
        {"from": "Company", "to": "Company", "label": "known_collaborator"},
        {"from": "Person", "to": "GovernmentBody", "label": "formerly_employed"},
        {"from": "Person", "to": "GovernmentBody", "label": "employed"},
        {"from": "GovernmentBody", "to": "Company", "label": "contracts"},
        {"from": "GovernmentBody", "to": "GovernmentBody", "label": "known_collaborator"},
    ]
    return jsonify({"nodes": nodes, "edges": edges})

@app.route("/full-graph")
def full_graph():
    # Return the full graph (all nodes and relationships)
    nodes = []
    edges = []
    seen_nodes = set()
    with driver.session() as session:
        # Person nodes
        for record in session.run("MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.title AS title"):
            if record["id"] not in seen_nodes:
                nodes.append({
                    "id": record["id"],
                    "label": record["name"],
                    "group": "Person",
                    "title": record["title"] or ""
                })
                seen_nodes.add(record["id"])
        # Company nodes
        for record in session.run("MATCH (c:Company) RETURN c.id AS id, c.name AS name"):
            if record["id"] not in seen_nodes:
                nodes.append({
                    "id": record["id"],
                    "label": record["name"],
                    "group": "Company",
                    "title": f"ID: {record['id']}"
                })
                seen_nodes.add(record["id"])
        # Government Body nodes
        for record in session.run("MATCH (g:`Government Body`) RETURN g.id AS id, g.name AS name"):
            if record["id"] not in seen_nodes:
                nodes.append({
                    "id": record["id"],
                    "label": record["name"],
                    "group": "GovernmentBody",
                    "title": f"ID: {record['id']}"
                })
                seen_nodes.add(record["id"])
        # Relationships
        for record in session.run("""
            MATCH (a)-[r]->(b)
            RETURN a.id AS from_id, b.id AS to_id, type(r) AS label, r.notes AS title
        """):
            edges.append({
                "from": record["from_id"],
                "to": record["to_id"],
                "label": record["label"],
                "title": record.get("title", ""),
                "arrows": "to"
            })
    return jsonify({"nodes": nodes, "edges": edges})

@app.route("/graph")
def graph_view():
    # Render the full graph visualization page
    return render_template("full_graph.html")

@app.route("/schema")
def schema_view():
    # Render the schema visualization page
    return render_template("schema.html")

@app.route("/network-analysis", methods=["GET", "POST"])
def network_analysis():
    results = None
    columns = []
    analysis_type = request.form.get("analysis_type", "gov_company")
    selected_company = selected_company1 = selected_company2 = None
    selected_gov = selected_gov1 = selected_gov2 = None
    selected_person1_name = selected_person2_name = None
    include_companies = request.form.get("include_companies") == "on"

    with driver.session() as session:
        companies = [dict(record) for record in session.run("MATCH (c:Company) RETURN c.id AS id, c.name AS name")]
        governments = [dict(record) for record in session.run("MATCH (g:`Government Body`) RETURN g.id AS id, g.name AS name")]
        people = [dict(record) for record in session.run("MATCH (p:Person) RETURN p.id AS id, p.name AS name")]

    if request.method == "POST":
        cypher = ""
        params = {}

        if analysis_type == "gov_company":
            government_id = request.form.get("government_id")
            company_id = request.form.get("company_id")
            selected_gov = government_id
            selected_company = company_id
            cypher = """
                MATCH (gov:`Government Body` {id: $government_id})
                MATCH (comp:Company {id: $company_id})
                MATCH (p1:Person)-[:employed|formerly_employed]-(gov)
                MATCH (p2:Person)-[:employed|formerly_employed]-(comp)
                MATCH path = shortestPath((p1)-[:knows|works_with*0..6]-(p2))
                WHERE all(n IN nodes(path)[1..-2] WHERE "Person" IN labels(n))
                RETURN
                    [{id: gov.id, label: coalesce(gov.name, gov.id), group: head(labels(gov)), title: coalesce(gov.title, gov.name, gov.id)}] +
                    [n IN nodes(path) | {id: n.id, label: coalesce(n.name, n.id), group: head(labels(n)), title: coalesce(n.title, n.name, n.id)}] +
                    [{id: comp.id, label: coalesce(comp.name, comp.id), group: head(labels(comp)), title: coalesce(comp.title, comp.name, comp.id)}] AS Path_Nodes,
                    [{from: p1.id, to: gov.id, label: 'employed', title: ''}] +
                    [r IN relationships(path) | {from: startNode(r).id, to: endNode(r).id, label: type(r), title: coalesce(r.notes, '')}] +
                    [{from: p2.id, to: comp.id, label: 'employed', title: ''}] AS Path_Edges
            """
            params = {"government_id": government_id, "company_id": company_id}

        elif analysis_type == "company_company":
            company1_id = request.form.get("company1_id")
            company2_id = request.form.get("company2_id")
            selected_company1 = company1_id
            selected_company2 = company2_id
            cypher = """
                MATCH (c1:Company {id: $company1_id})
                MATCH (c2:Company {id: $company2_id})
                MATCH (p1:Person)-[r1:employed|formerly_employed]-(c1)
                MATCH (p2:Person)-[r2:employed|formerly_employed]-(c2)
                MATCH path = shortestPath((p1)-[:knows|works_with*0..6]-(p2))
                WHERE all(n IN nodes(path)[1..-2] WHERE "Person" IN labels(n))
                RETURN
                    [{id: c1.id, label: coalesce(c1.name, c1.id), group: head(labels(c1)), title: coalesce(c1.title, c1.name, c1.id)}] +
                    [n IN nodes(path) | {id: n.id, label: coalesce(n.name, n.id), group: head(labels(n)), title: coalesce(n.title, n.name, n.id)}] +
                    [{id: c2.id, label: coalesce(c2.name, c2.id), group: head(labels(c2)), title: coalesce(c2.title, c2.name, c2.id)}] AS Path_Nodes,
                    [{from: p1.id, to: c1.id, label: type(r1), title: coalesce(r1.notes, '')}] +
                    [r IN relationships(path) | {from: startNode(r).id, to: endNode(r).id, label: type(r), title: coalesce(r.notes, '')}] +
                    [{from: p2.id, to: c2.id, label: type(r2), title: coalesce(r2.notes, '')}] AS Path_Edges
            """
            params = {"company1_id": company1_id, "company2_id": company2_id}

        elif analysis_type == "gov_gov":
            government1_id = request.form.get("government1_id")
            government2_id = request.form.get("government2_id")
            selected_gov1 = government1_id
            selected_gov2 = government2_id
            cypher = """
                MATCH (g1:`Government Body` {id: $government1_id})
                MATCH (g2:`Government Body` {id: $government2_id})
                MATCH (p1:Person)-[r1:employed|formerly_employed]-(g1)
                MATCH (p2:Person)-[r2:employed|formerly_employed]-(g2)
                MATCH path = shortestPath((p1)-[:knows|works_with*0..6]-(p2))
                WHERE all(n IN nodes(path)[1..-2] WHERE "Person" IN labels(n))
                RETURN
                    [{id: g1.id, label: coalesce(g1.name, g1.id), group: head(labels(g1)), title: coalesce(g1.title, g1.name, g1.id)}] +
                    [n IN nodes(path) | {id: n.id, label: coalesce(n.name, n.id), group: head(labels(n)), title: coalesce(n.title, n.name, n.id)}] +
                    [{id: g2.id, label: coalesce(g2.name, g2.id), group: head(labels(g2)), title: coalesce(g2.title, g2.name, g2.id)}] AS Path_Nodes,
                    [{from: p1.id, to: g1.id, label: type(r1), title: coalesce(r1.notes, '')}] +
                    [r IN relationships(path) | {from: startNode(r).id, to: endNode(r).id, label: type(r), title: coalesce(r.notes, '')}] +
                    [{from: p2.id, to: g2.id, label: type(r2), title: coalesce(r2.notes, '')}] AS Path_Edges
            """
            params = {"government1_id": government1_id, "government2_id": government2_id}

        elif analysis_type == "person_person":
            person1_input = request.form.get("person1_name", "").strip()
            person2_input = request.form.get("person2_name", "").strip()
            selected_person1_name = person1_input
            selected_person2_name = person2_input

            def extract_id(val):
                match = re.match(r".*\[([^\[\]]+)\]$", val)
                if match:
                    return match.group(1)
                return None

            person1_id = extract_id(person1_input)
            person2_id = extract_id(person2_input)

            with driver.session() as session:
                if not person1_id and person1_input:
                    rec = session.run("MATCH (p:Person) WHERE p.name = $val OR p.id = $val RETURN p.id AS id", val=person1_input).single()
                    person1_id = rec["id"] if rec else None
                if not person2_id and person2_input:
                    rec = session.run("MATCH (p:Person) WHERE p.name = $val OR p.id = $val RETURN p.id AS id", val=person2_input).single()
                    person2_id = rec["id"] if rec else None

            if person1_id and person2_id:
                cypher = """
                    MATCH (p1:Person {id: $person1_id})
                    MATCH (p2:Person {id: $person2_id})
                    MATCH path = shortestPath((p1)-[:knows|works_with*0..6]-(p2))
                    WHERE all(n IN nodes(path)[1..-2] WHERE "Person" IN labels(n))
                    RETURN
                        [n IN nodes(path) | {id: n.id, label: coalesce(n.name, n.id), group: head(labels(n)), title: coalesce(n.title, n.name, n.id)}] AS Path_Nodes,
                        [r IN relationships(path) | {from: startNode(r).id, to: endNode(r).id, label: type(r), title: coalesce(r.notes, '')}] AS Path_Edges
                """
                params = {"person1_id": person1_id, "person2_id": person2_id}
            else:
                results = [{"Error": "One or both persons not found."}]
                columns = ["Error"]

        if cypher:
            with driver.session() as session:
                try:
                    result = session.run(cypher, **params)
                    results = [dict(record) for record in result]
                    columns = ["Path_Nodes", "Path_Edges"]
                except Exception as e:
                    results = [{"Error": str(e)}]
                    columns = ["Error"]

    return render_template(
        "network_analysis.html",
        companies=companies,
        governments=governments,
        people=people,
        results=results,
        columns=columns,
        analysis_type=analysis_type,
        selected_company=selected_company,
        selected_company1=selected_company1,
        selected_company2=selected_company2,
        selected_gov=selected_gov,
        selected_gov1=selected_gov1,
        selected_gov2=selected_gov2,
        selected_person1_name=selected_person1_name,
        selected_person2_name=selected_person2_name,
        include_companies=include_companies,
    )

@app.route("/add", methods=["GET", "POST"])
def add():
    # Add node or relationship via form
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "node":
            node_type = request.form.get("node_type")
            name = request.form.get("name")
            node_id = request.form.get("id")
            title = request.form.get("title", "")
            if not node_type or not name or not node_id:
                message = "Missing required fields for node."
            else:
                cypher = f"CREATE (n:`{node_type}` {{id: $id, name: $name"
                params = {"id": node_id, "name": name}
                if node_type == "Person" and title:
                    cypher += ", title: $title"
                    params["title"] = title
                cypher += "})"
                with driver.session() as session:
                    session.run(cypher, **params)
                message = "Node added!"
        elif action == "relationship":
            from_id = request.form.get("from_id")
            to_id = request.form.get("to_id")
            rel_type = request.form.get("rel_type")
            notes = request.form.get("notes", "")
            if not from_id or not to_id or not rel_type:
                message = "Missing required fields for relationship."
            else:
                cypher = f"""
                    MATCH (a{{id: $from_id}})
                    MATCH (b{{id: $to_id}})
                    MERGE (a)-[r:`{rel_type}`]->(b)
                    SET r.notes = $notes
                """
                params = {"from_id": from_id, "to_id": to_id, "notes": notes}
                with driver.session() as session:
                    session.run(cypher, **params)
                message = "Relationship added!"
    return render_template("add.html", message=message)

@app.route("/delete", methods=["GET", "POST"])
def delete():
    # Delete node or relationship via form
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "node":
            node_id = request.form.get("id")
            if not node_id:
                message = "Missing node ID."
            else:
                cypher = "MATCH (n {id: $id}) DETACH DELETE n"
                with driver.session() as session:
                    session.run(cypher, id=node_id)
                message = f"Node '{node_id}' and its relationships deleted (if they existed)."
        elif action == "relationship":
            from_id = request.form.get("from_id")
            to_id = request.form.get("to_id")
            rel_type = request.form.get("rel_type")
            if not from_id or not to_id or not rel_type:
                message = "Missing required fields for relationship."
            else:
                cypher = f"""
                    MATCH (a {{id: $from_id}})-[r:`{rel_type}`]->(b {{id: $to_id}})
                    DELETE r
                """
                with driver.session() as session:
                    session.run(cypher, from_id=from_id, to_id=to_id)
                message = f"Relationship '{rel_type}' from '{from_id}' to '{to_id}' deleted."
    return render_template("delete.html", message=message)

@app.route("/export-json")
def export_json():
    # Export the entire graph as JSON
    data = {
        "entities": {
            "people": [],
            "companies": [],
            "government_bodies": []
        },
        "relationships": {
            "person_company": [],
            "person_government": [],
            "person_person": [],
            "company_company": [],
            "company_government": [],
            "government_government": []
        }
    }
    with driver.session() as session:
        # People
        people = session.run("MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.title AS title")
        data["entities"]["people"] = [dict(record) for record in people]
        # Companies
        companies = session.run("MATCH (c:Company) RETURN c.id AS id, c.name AS name")
        data["entities"]["companies"] = [dict(record) for record in companies]
        # Government Bodies
        govs = session.run("MATCH (g:`Government Body`) RETURN g.id AS id, g.name AS name")
        data["entities"]["government_bodies"] = [dict(record) for record in govs]
        # Relationships
        pc = session.run("""
            MATCH (p:Person)-[r]->(c:Company)
            RETURN p.id AS person_id, c.id AS company_id, type(r) AS type, r.notes AS notes
        """)
        data["relationships"]["person_company"] = [dict(record) for record in pc]
        pg = session.run("""
            MATCH (p:Person)-[r]->(g:`Government Body`)
            RETURN p.id AS person_id, g.id AS government_id, type(r) AS type, r.notes AS notes
        """)
        data["relationships"]["person_government"] = [dict(record) for record in pg]
        pp = session.run("""
            MATCH (p1:Person)-[r]->(p2:Person)
            RETURN p1.id AS person_id_1, p2.id AS person_id_2, type(r) AS type, r.notes AS notes
        """)
        data["relationships"]["person_person"] = [dict(record) for record in pp]
        cc = session.run("""
            MATCH (c1:Company)-[r]->(c2:Company)
            RETURN c1.id AS company_id_1, c2.id AS company_id_2, type(r) AS type, r.notes AS notes
        """)
        data["relationships"]["company_company"] = [dict(record) for record in cc]
        cg = session.run("""
            MATCH (c:Company)-[r]->(g:`Government Body`)
            RETURN c.id AS company_id, g.id AS government_id, type(r) AS type, r.notes AS notes
        """)
        data["relationships"]["company_government"] = [dict(record) for record in cg]
        gg = session.run("""
            MATCH (g1:`Government Body`)-[r]->(g2:`Government Body`)
            RETURN g1.id AS government_id_1, g2.id AS government_id_2, type(r) AS type, r.notes AS notes
        """)
        data["relationships"]["government_government"] = [dict(record) for record in gg]

    return Response(
        json.dumps(data, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=export.json"}
    )

@app.route("/edit", methods=["GET", "POST"])
def edit():
    # Edit node and its relationships
    message = None
    node = None
    relationships = []
    all_nodes = []
    if request.method == "POST":
        node_id = request.form.get("id")
        node_type = request.form.get("node_type")
        name = request.form.get("name")
        title = request.form.get("title", "")
        # Update node properties
        if not node_id or not node_type or not name:
            message = "Missing required fields."
        else:
            cypher = f"""
                MATCH (n:`{node_type}` {{id: $id}})
                SET n.name = $name
                {', n.title = $title' if node_type == 'Person' else ''}
            """
            params = {"id": node_id, "name": name}
            if node_type == "Person":
                params["title"] = title
            with driver.session() as session:
                session.run(cypher, **params)
            message = "Node updated!"

        # Update relationship notes
        rel_ids = request.form.getlist("rel_id")
        rel_notes = request.form.getlist("rel_notes")
        rel_types = request.form.getlist("rel_type")
        rel_targets = request.form.getlist("rel_target")
        for rid, rtype, rtarget, rnotes in zip(rel_ids, rel_types, rel_targets, rel_notes):
            with driver.session() as session:
                session.run(
                    f"""
                    MATCH (a {{id: $from_id}})-[r:`{rtype}`]->(b {{id: $to_id}})
                    SET r.notes = $notes
                    """,
                    {"from_id": node_id, "to_id": rtarget, "notes": rnotes}
                )

        # Delete relationships
        del_rels = request.form.getlist("delete_rel")
        for del_rel in del_rels:
            rtype, rtarget = del_rel.split("||")
            with driver.session() as session:
                session.run(
                    f"""
                    MATCH (a {{id: $from_id}})-[r:`{rtype}`]->(b {{id: $to_id}})
                    DELETE r
                    """,
                    {"from_id": node_id, "to_id": rtarget}
                )

        # Add new relationship
        new_rel_type = request.form.get("new_rel_type")
        new_rel_target = request.form.get("new_rel_target")
        new_rel_notes = request.form.get("new_rel_notes")
        if new_rel_type and new_rel_target:
            with driver.session() as session:
                session.run(
                    f"""
                    MATCH (a {{id: $from_id}})
                    MATCH (b {{id: $to_id}})
                    MERGE (a)-[r:`{new_rel_type}`]->(b)
                    SET r.notes = $notes
                    """,
                    {"from_id": node_id, "to_id": new_rel_target, "notes": new_rel_notes or ""}
                )
            message = "Node and relationships updated!"

        # Fetch updated node and relationships for display
        with driver.session() as session:
            node = session.run(
                f"MATCH (n:`{node_type}` {{id: $id}}) RETURN n.id AS id, n.name AS name, n.title AS title",
                id=node_id
            ).single()
            rels = session.run(
                """
                MATCH (a {id: $id})-[r]->(b)
                RETURN id(r) AS rel_id, type(r) AS type, b.id AS target_id, b.name AS target_name, r.notes AS notes
                """,
                id=node_id
            )
            relationships = [dict(record) for record in rels]
            # For adding new relationships, get all other nodes
            all_nodes = session.run(
                "MATCH (n) WHERE n.id <> $id RETURN n.id AS id, n.name AS name, labels(n)[0] AS type", id=node_id
            ).data()
    else:
        # GET: fetch node and relationships
        node_id = request.args.get("id")
        node_type = request.args.get("node_type")
        if node_id and node_type:
            with driver.session() as session:
                node = session.run(
                    f"MATCH (n:`{node_type}` {{id: $id}}) RETURN n.id AS id, n.name AS name, n.title AS title",
                    id=node_id
                ).single()
                rels = session.run(
                    """
                    MATCH (a {id: $id})-[r]->(b)
                    RETURN id(r) AS rel_id, type(r) AS type, b.id AS target_id, b.name AS target_name, r.notes AS notes
                    """,
                    id=node_id
                )
                relationships = [dict(record) for record in rels]
                all_nodes = session.run(
                    "MATCH (n) WHERE n.id <> $id RETURN n.id AS id, n.name AS name, labels(n)[0] AS type", id=node_id
                ).data()
    return render_template("edit.html", node=node, message=message, relationships=relationships, all_nodes=all_nodes)

from flask import request, jsonify

@app.route("/api/node")
def api_get_node():
    # API endpoint to get a node's details
    node_id = request.args.get("id")
    node_type = request.args.get("node_type")
    with driver.session() as session:
        node = session.run(
            f"MATCH (n:`{node_type}` {{id: $id}}) RETURN n.id AS id, n.name AS name, n.title AS title",
            id=node_id
        ).single()
    if node:
        return jsonify(dict(node))
    return jsonify({"error": "Node not found"}), 404

@app.route("/api/node", methods=["POST"])
def api_update_node():
    # API endpoint to update a node's details
    node_id = request.form.get("id")
    node_type = request.form.get("node_type")
    name = request.form.get("name")
    title = request.form.get("title", "")
    if not node_id or not node_type or not name:
        return jsonify({"success": False, "error": "Missing fields"})
    cypher = f"""
        MATCH (n:`{node_type}` {{id: $id}})
        SET n.name = $name
        {', n.title = $title' if node_type == 'Person' else ''}
    """
    params = {"id": node_id, "name": name}
    if node_type == "Person":
        params["title"] = title
    with driver.session() as session:
        session.run(cypher, **params)
    return jsonify({"success": True})

@app.route("/api/relationship", methods=["POST"])
def api_update_relationship():
    # API endpoint to update a relationship's type or notes
    from_id = request.form.get("from")
    to_id = request.form.get("to")
    old_type = request.form.get("old_type")
    new_type = request.form.get("new_type")
    notes = request.form.get("notes", "")
    if not from_id or not to_id or not old_type or not new_type:
        return jsonify({"success": False, "error": "Missing fields"})
    with driver.session() as session:
        if old_type == new_type:
            # Only update notes
            session.run(
                f"""
                MATCH (a {{id: $from_id}})-[r:`{old_type}`]->(b {{id: $to_id}})
                SET r.notes = $notes
                """,
                {"from_id": from_id, "to_id": to_id, "notes": notes}
            )
        else:
            # Change type: delete old, create new with notes
            session.run(
                f"""
                MATCH (a {{id: $from_id}})-[r:`{old_type}`]->(b {{id: $to_id}})
                DELETE r
                """,
                {"from_id": from_id, "to_id": to_id}
            )
            session.run(
                f"""
                MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
                MERGE (a)-[r:`{new_type}`]->(b)
                SET r.notes = $notes
                """,
                {"from_id": from_id, "to_id": to_id, "notes": notes}
            )
    return jsonify({"success": True})

@app.route("/api/relationship-types")
def api_relationship_types():
    # API endpoint to get all relationship types in the database
    with driver.session() as session:
        result = session.run("CALL db.relationshipTypes()")
        types = [record["relationshipType"] for record in result]
    return jsonify(types)

@app.route("/api/person-names")
def api_person_names():
    # API endpoint to get all person names and IDs
    with driver.session() as session:
        result = session.run("MATCH (p:Person) RETURN p.name AS name, p.id AS id")
        names = [{"name": record["name"], "id": record["id"]} for record in result]
    return jsonify(names)

@app.route("/api/company-names")
def api_company_names():
    # API endpoint to get all company names and IDs
    with driver.session() as session:
        result = session.run("MATCH (c:Company) RETURN c.name AS name, c.id AS id")
        names = [{"name": record["name"], "id": record["id"]} for record in result]
    return jsonify(names)

@app.route("/api/add-node", methods=["POST"])
def api_add_node():
    # API endpoint to add a new node
    node_type = request.form.get("node_type")
    node_id = request.form.get("id")
    name = request.form.get("name")
    title = request.form.get("title", "")
    if not node_type or not node_id or not name:
        return jsonify({"success": False, "error": "Missing required fields"})
    cypher = f"CREATE (n:`{node_type}` {{id: $id, name: $name"
    params = {"id": node_id, "name": name}
    if node_type == "Person" and title:
        cypher += ", title: $title"
        params["title"] = title
    cypher += "})"
    with driver.session() as session:
        session.run(cypher, **params)
    return jsonify({"success": True})

@app.route("/api/add-relationship", methods=["POST"])
def api_add_relationship():
    # API endpoint to add a new relationship
    from_id = request.form.get("from_id")
    to_id = request.form.get("to_id")
    rel_type = request.form.get("rel_type")
    notes = request.form.get("notes", "")
    if not from_id or not to_id or not rel_type:
        return jsonify({"success": False, "error": "Missing required fields"})
    cypher = f"""
        MATCH (a{{id: $from_id}})
        MATCH (b{{id: $to_id}})
        MERGE (a)-[r:`{rel_type}`]->(b)
        SET r.notes = $notes
    """
    params = {"from_id": from_id, "to_id": to_id, "notes": notes}
    with driver.session() as session:
        session.run(cypher, **params)
    return jsonify({"success": True})

@app.route("/api/node-ids")
def api_node_ids():
    # API endpoint to get all node IDs, names, and types
    with driver.session() as session:
        result = session.run("MATCH (n) RETURN n.id AS id, n.name AS name, labels(n)[0] AS type")
        nodes = [{"id": record["id"], "name": record["name"], "type": record["type"]} for record in result]
    return jsonify(nodes)

@app.route("/api/node-relations")
def api_node_relations():
    # API endpoint to get all relationships for a given node
    node_id = request.args.get("id")
    if not node_id:
        return {"error": "Missing id"}, 400
    with driver.session() as session:
        result = session.run("""
            MATCH (n {id: $id})-[r]-(m)
            RETURN type(r) AS rel_type, r.notes AS notes, m.id AS other_id, m.name AS other_name, labels(m)[0] AS other_type, startNode(r).id AS from_id, endNode(r).id AS to_id
        """, id=node_id)
        relations = [dict(record) for record in result]
    return jsonify(relations)

#if __name__ == "__main__":
    #app.run(host='0.0.0.0', port=5000, debug=True)