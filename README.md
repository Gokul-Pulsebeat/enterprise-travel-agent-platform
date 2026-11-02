# Flight Agent MCP Learning Lab

This is a deliberately small project for learning the moving parts around:

- a normal business web service
- an MCP server that exposes that service as tools
- an AI agent that receives user prompts and calls those MCP tools
- the MCP client, which lives inside the agent

The business logic is intentionally tiny. The goal is to understand the architecture, not to build a real travel system.

## Architecture

```text
User prompt
  -> agent/agent.py
      - contains simple "agent" logic
      - contains the MCP client
      - connects to multiple MCP servers over stdio
  -> mcp_server/server.py
      - exposes tools like search_flights and get_flight
      - calls the flight API over HTTP
  -> flight_api/app.py
      - normal REST API
      - reads mock flights from SQLite
  -> flight_api/flights.db
  -> hotel_mcp_server/server.py
      - exposes tools like search_hotels and get_hotel
      - calls the hotel API over HTTP
  -> hotel_api/app.py
      - normal REST API
      - reads mock hotels from SQLite
  -> hotel_api/hotels.db
```

## Where The MCP Client Fits

The MCP client is not a separate business service in this simple version.

It is the part of the agent that knows how to:

1. start or connect to MCP servers
2. ask each MCP server which tools exist
3. combine those tools into one catalog
4. call the selected server/tool with arguments
4. return the tool result back to the agent logic

So the agent has two responsibilities:

- decide what to do based on the user's prompt
- use the MCP client to call tools when it needs outside information

In this project, `agent/agent.py` contains both the simple agent logic and the MCP client code.

## Project Folders

```text
flight_api/         Normal web service with public flight search APIs
mcp_server/         MCP server that wraps the flight API as tools
hotel_api/          Normal web service with public hotel search APIs
hotel_mcp_server/   MCP server that wraps the hotel API as tools
agent/              Simple prompt-driven agent and MCP client
```

## Install

Use Python 3.11+ if possible.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS/Linux, activate with:

```bash
source .venv/bin/activate
```

## Run Version 1

Terminal 1: start the flight API.

```bash
uvicorn flight_api.app:app --reload --port 8000
```

Terminal 2: start the hotel API.

```bash
uvicorn hotel_api.app:app --reload --port 8001
```

Try it:

```bash
curl "http://127.0.0.1:8000/flights?origin=BLR&destination=DEL"
curl "http://127.0.0.1:8000/flights/1"
curl "http://127.0.0.1:8001/hotels?city=Delhi"
curl "http://127.0.0.1:8001/hotels/1"
```

Terminal 3: run the agent.

```bash
python agent/agent.py "Find flights from BLR to DEL"
python agent/agent.py "Find hotels in Delhi"
python agent/agent.py "What travel tools can you use?"
```

The agent starts both MCP servers as subprocesses, builds one combined tool catalog, then calls the selected server/tool.

## Use A Free Local LLM

The default real-LLM provider is now Ollama. It runs open models locally, so you do not need an OpenAI subscription or an OpenAI API key.

Install Ollama from:

```text
https://ollama.com
```

Then pull a small model:

```powershell
ollama pull llama3.2
```

Start the flight API in terminal 1:

```powershell
.\.venv\Scripts\activate
uvicorn flight_api.app:app --reload --port 8000
```

Start the hotel API in terminal 2:

```powershell
.\.venv\Scripts\activate
uvicorn hotel_api.app:app --reload --port 8001
```

Run the agent in terminal 3:

```powershell
.\.venv\Scripts\activate
$env:LLM_PROVIDER="ollama"
$env:OLLAMA_MODEL="llama3.2"
python agent/agent.py "Find the cheapest flights from BLR to DEL"
python agent/agent.py "Find hotels in Delhi"
```

The flight and hotel APIs do not need any LLM key. Only the agent talks to the LLM.

## Use OpenAI Instead

OpenAI is still supported as an optional provider. To use it, set `LLM_PROVIDER=openai` and provide `OPENAI_API_KEY` only in the agent terminal.

PowerShell:

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-5.2"
python agent/agent.py "Find the cheapest flights from BLR to DEL"
```

macOS/Linux:

```bash
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_MODEL="gpt-5.2"
python agent/agent.py "Find the cheapest flights from BLR to DEL"
```

With a real LLM provider, the flow becomes:

```text
User prompt
  -> LLM creates a multi-step execution plan
  -> MCP client runs independent steps in parallel
  -> MCP client waits when a step depends on another step
  -> MCP servers call their business APIs
  -> LLM summarizes all step results for the user
```

This project intentionally uses the LLM in a simple JSON-planning loop instead of a full agent framework. That keeps the MCP client/server boundary and workflow execution easy to see.

The planner returns JSON like this:

```json
{
  "steps": [
    {
      "step_id": "search_flights",
      "server_name": "flight",
      "tool_name": "search_flights",
      "arguments": {
        "origin": "BLR",
        "destination": "DEL",
        "date": "2026-06-10"
      },
      "depends_on": []
    },
    {
      "step_id": "search_hotels",
      "server_name": "hotel",
      "tool_name": "search_hotels",
      "arguments": {
        "city": "Delhi",
        "check_in_date": "2026-06-10"
      },
      "depends_on": []
    }
  ]
}
```

If a later step needs an earlier result, it uses `depends_on`. For example, hotel search can wait for flight search and use the first flight date:

```json
{
  "step_id": "search_hotels",
  "server_name": "hotel",
  "tool_name": "search_hotels",
  "arguments": {
    "city": "Delhi",
    "check_in_date": "$first_flight_date:search_flights"
  },
  "depends_on": ["search_flights"]
}
```

## Use The Mock Planner

If you want to test without any LLM at all:

```powershell
$env:LLM_PROVIDER="mock"
python agent/agent.py "Find flights from BLR to DEL"
python agent/agent.py "Find hotels in Delhi"
python agent/agent.py "Help me travel from Bangalore to Delhi on 2026-06-10 and stay there"
python agent/agent.py "Find a flight from Bangalore to Delhi and then find hotels based on when I arrive"
```

## LangChain Or LangGraph?

Not yet.

For version 1, the workflow is linear:

```text
prompt -> choose tool -> call MCP tool -> summarize result
```

LangGraph becomes useful when the workflow has branches, loops, memory, retries, approvals, or multiple agents. For example, booking a ticket in version 2 could become:

```text
search flights -> ask user to choose -> verify auth -> reserve seat -> mock payment -> confirm booking
```

That is a better time to introduce LangGraph. For now, a small provider switch keeps the architecture easier to understand.

## Version 1 API

Public endpoints:

```text
GET /health
GET /flights
GET /flights?origin=BLR&destination=DEL
GET /flights?origin=BLR&destination=DEL&date=2026-06-10
GET /flights/{flight_id}
GET /hotels
GET /hotels?city=Delhi
GET /hotels?city=Delhi&check_in_date=2026-06-10
GET /hotels/{hotel_id}
```

## Version 2 Ideas

Later, add:

- `users` table
- `bookings` table
- `POST /auth/register`
- `POST /auth/login`
- `POST /bookings`
- `GET /bookings/me`
- bearer-token authentication
- MCP tools like `book_flight` and `list_my_bookings`

For this learning project, do not start with OAuth. First use a simple login endpoint that returns a bearer token. OAuth is useful later when a user authorizes your agent to access a separate third-party service.
