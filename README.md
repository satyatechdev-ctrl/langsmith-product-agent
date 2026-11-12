# LangSmith Product Database Agent

A LangChain agent that answers natural-language questions about product names,
prices, descriptions, and inventory. The app exports a LangGraph-compatible
factory and includes a `langgraph.json` deployment manifest for LangSmith
Deployment.

The agent can answer questions such as:

- What is the average price of products with more than 100 units in stock?
- List the names and descriptions of products that cost less than $50 and have
  the word "durable" in their description.
- Which products have the highest inventory, and what are their prices?

## Architecture and safeguards

- LangChain `create_agent` runs a tool-calling agent and is exported as a graph
  factory for the LangGraph/LangSmith runtime.
- The SQL tool is restricted to read-only `SELECT` queries against the
  `products` table and its documented columns.
- SQL is parsed before execution; multiple statements, non-SELECT statements,
  other tables, unsupported functions, and unknown columns are rejected.
- Results are capped at 100 rows. PostgreSQL queries run in read-only
  transactions with a statement timeout; SQLite connections are query-only.
- In production, use a dedicated database account with `SELECT` permission only
  on `products`, network access restricted to the agent, and a managed
  PostgreSQL database. The local SQLite database is for development only.

SQL validation is defense in depth, not a substitute for database permissions.
Treat product descriptions as untrusted content; the agent is instructed not to
follow instructions found in database rows.

## Database schema

The production PostgreSQL schema is in [`sql/schema.sql`](sql/schema.sql). It
defines:

| Column | Type | Constraints |
|---|---|---|
| `id` | integer | Primary key |
| `name` | varchar(200) | Required |
| `price` | numeric(10, 2) | Required, non-negative |
| `description` | text | Required |
| `inventory` | integer | Required, non-negative |

[`sql/seed.sql`](sql/seed.sql) contains optional sample rows. The
`product_agent` SQLAlchemy model is the schema used by the local initializer
and tests. For production database evolution, manage schema changes with your
organization's migration process rather than running `create_all` at runtime.

## Setup

Requires Python 3.10–3.13 and `uv`.

```powershell
cd langsmith-product-agent
uv sync --extra dev
Copy-Item .env.example .env
```

Set `EURON_API_KEY` in `.env` (or in the shell). The agent uses Euron's
`euri-reasoning` model and OpenAI-compatible endpoint by default; override
these with `EURON_MODEL` and `EURON_BASE_URL` if needed. The agent requires
`EURON_API_KEY` and does not fall back to `OPENAI_API_KEY`. Keep credentials
out of source control. `LANGSMITH_API_KEY` and tracing settings are optional
locally; to send traces, set a valid key and change `LANGSMITH_TRACING` to
`true`. Configure deployment credentials as LangSmith Deployment secrets.

Create a local SQLite database and optionally load the sample products:

```powershell
uv run python -m product_agent.init_db --seed
```

The initializer is explicit and idempotent: it creates missing tables, and
`--seed` inserts examples only when the table is empty. It does not run when the
agent starts.

## Run and test locally

Invoke the agent directly:

```powershell
uv run python -c "from product_agent.graph import make_graph; g = make_graph(); r = g.invoke({'messages': [{'role': 'user', 'content': 'What is the average price of products with more than 100 units in stock?'}]}); print(r['messages'][-1].content)"
```

Start the LangGraph development server and open the local deployment in
LangSmith Studio:

```powershell
uv run langgraph dev
```

Run the test suite and linter:

```powershell
uv run pytest
uv run ruff check src tests
```

## Deploy to LangSmith

1. Confirm your LangSmith account and deployment plan meet the current
   [LangSmith Deployment prerequisites](https://docs.langchain.com/langsmith/deployment-quickstart).
2. Push this project to a Git repository, or use the LangGraph CLI from the
   project directory.
3. Configure `EURON_API_KEY`, `DATABASE_URL`, and (if tracing is desired)
   `LANGSMITH_API_KEY` as deployment secrets. Never put production credentials
   in `langgraph.json` or commit a real `.env` file.
4. Ensure the hosted runtime can securely reach the database. Use managed
   PostgreSQL and a least-privilege read-only database role; do not use the
   local SQLite path for a hosted deployment.
5. Deploy through the LangSmith UI or, after reviewing the target and any
   associated charges, use:

   ```powershell
   uv run langgraph deploy
   ```

The deployment graph ID is `product_agent`. See the official
[LangSmith Deployment quickstart](https://docs.langchain.com/langsmith/deployment-quickstart)
for account, CLI, deployment, and post-deployment testing steps.

## Automated GitHub deployment

The [GitHub Actions workflow](.github/workflows/deploy.yml) runs tests and lint
on pull requests to `main`. After those checks pass, pushes to `main` and
manually started workflow runs deploy or update the `langsmith-product-agent`
serverless deployment.

In the repository's **Settings → Environments**, create a `production`
environment and add these environment secrets:

| Secret | Purpose |
|---|---|
| `LANGSMITH_API_KEY` | Authenticates the LangGraph CLI deployment |
| `EURON_API_KEY` | Authenticates the Euron model at runtime |
| `DATABASE_URL` | Production PostgreSQL connection URL |

Optionally add `EURON_MODEL` and `EURON_BASE_URL` as environment variables in
that same GitHub environment; they default to `euri-reasoning` and
`https://api.euron.one/api/v1/euri`. The workflow writes the model key and
database URL to a temporary, ignored `.env` file so LangSmith receives them as
deployment environment values; the LangSmith API key is used only by the CLI.
The temporary file is removed after deployment. Protect `main` with required
checks and restrict access to the `production` environment before enabling
automatic deployments. LangSmith hosting may incur charges.

## Example SQL queries

These are compatible with the supported SQLite and PostgreSQL dialects:

```sql
SELECT AVG(price) AS average_price
FROM products
WHERE inventory > 100;
```

```sql
SELECT name, description
FROM products
WHERE price < 50
  AND LOWER(description) LIKE '%durable%'
ORDER BY name;
```

The agent generates equivalent read-only queries from natural-language input;
these examples can also be run directly in a SQL client.
