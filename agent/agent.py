# Import `asyncio` so the agent can run MCP tool calls concurrently.
import asyncio

# Import `json` so the agent can exchange structured plans and tool results.
import json

# Import `os` so the agent can read environment variables.
import os

# Import `re` so the mock planner can extract airport codes and dates.
import re

# Import `sys` so the command-line program can read arguments and locate Python.
import sys

# Import `AsyncExitStack` so multiple MCP server sessions can stay open together.
from contextlib import AsyncExitStack

# Import `Path` so script paths are built safely across operating systems.
from pathlib import Path

# Import `requests` so the agent can call Ollama's local HTTP API.
import requests

# Import specific request exceptions so setup failures can be shown clearly.
from requests import ConnectionError as RequestsConnectionError

# Import timeout exceptions so slow local model runs produce useful messages.
from requests import ReadTimeout

# Import MCP client classes used to connect to MCP servers.
from mcp import ClientSession, StdioServerParameters

# Import the stdio MCP client helper.
from mcp.client.stdio import stdio_client


# Compile a pattern that matches demo airport codes like BLR and DEL.
AIRPORT_CODE_PATTERN = re.compile(r"\b[A-Z]{3}\b")

# Compile a pattern that matches simple ISO dates like 2026-06-10.
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Define the small set of airport codes known by this demo database.
KNOWN_AIRPORT_CODES = {"BLR", "DEL", "BOM", "MAA"}

# Map common city names to demo airport codes.
CITY_TO_AIRPORT = {
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "delhi": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "chennai": "MAA",
}

# Map demo airport codes back to hotel city names.
AIRPORT_TO_CITY = {
    "BLR": "Bengaluru",
    "DEL": "Delhi",
    "BOM": "Mumbai",
    "MAA": "Chennai",
}

# Find the project root by going one folder above this file.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Configure all MCP servers that the agent can start and use.
MCP_SERVER_PATHS = {
    "flight": PROJECT_ROOT / "flight_mcp_server" / "server.py",
    "hotel": PROJECT_ROOT / "hotel_mcp_server" / "server.py",
}

# Environment variables forwarded to the MCP server subprocesses.
# `stdio_client` only inherits a small safe allowlist (PATH, HOME, ...), so anything else the
# servers need, such as the REST API URLs, must be passed explicitly. Without this, setting
# FLIGHT_API_BASE_URL/HOTEL_API_BASE_URL on the agent (for example in Docker) would have no effect.
MCP_FORWARDED_ENV_VARS = ("FLIGHT_API_BASE_URL", "HOTEL_API_BASE_URL")

# Read which LLM provider to use; `ollama` is the free local default.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Read the optional OpenAI model name.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

# Read Ollama's local base URL.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Read the Ollama model name.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# Read the Ollama timeout in seconds.
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))


# Define a tiny debug printer so LLM internals are visible while learning.
def debug_print(title: str, value) -> None:
    # Print a section header that makes the debug output easy to scan.
    print(f"\n--- {title} ---", file=sys.stderr)
    # If the value is a dict or list, pretty-print it as JSON.
    if isinstance(value, (dict, list)):
        # Print structured values in indented JSON form.
        print(json.dumps(value, indent=2), file=sys.stderr)
    # Otherwise print the value directly as text.
    else:
        # Print plain text values.
        print(value, file=sys.stderr)


# Define a helper that extracts known airport codes from a prompt.
def extract_airport_codes(prompt: str) -> list[str]:
    # Return only regex matches that exist in the demo airport code set.
    return [code for code in AIRPORT_CODE_PATTERN.findall(prompt.upper()) if code in KNOWN_AIRPORT_CODES]


# Define a helper that extracts the first ISO date from a prompt.
def extract_date(prompt: str) -> str | None:
    # Search for a date like `2026-06-10`.
    match = DATE_PATTERN.search(prompt)
    # Return the matched date text, or `None` if no date was present.
    return match.group(0) if match else None


# Define a helper that maps city names in the prompt to airport codes.
def find_city_airports(prompt: str) -> list[str]:
    # Convert the prompt to lowercase for case-insensitive city matching.
    prompt_lower = prompt.lower()
    # Return airport codes for city names that appear in the prompt.
    return [airport for city, airport in CITY_TO_AIRPORT.items() if city in prompt_lower]


# Define a helper that chooses origin and destination from a prompt for mock mode.
def infer_route(prompt: str) -> tuple[str, str] | None:
    # Prefer explicit airport codes like BLR and DEL.
    airport_codes = extract_airport_codes(prompt)
    # If two explicit airport codes exist, use the first as origin and second as destination.
    if len(airport_codes) >= 2:
        # Return a route tuple.
        return airport_codes[0], airport_codes[1]

    # Fall back to city-name mapping.
    city_airports = find_city_airports(prompt)
    # If two city airports were found, use their order from the city map as a simple demo route.
    if len(city_airports) >= 2:
        # Return a route tuple.
        return city_airports[0], city_airports[1]

    # Return `None` when the mock planner cannot infer a route.
    return None


# Define a helper that creates one executable plan step.
def make_step(
    step_id: str, server_name: str, tool_name: str, arguments: dict, depends_on: list[str] | None = None
) -> dict:
    # Return the normalized step dictionary used by the executor.
    return {
        "step_id": step_id,
        "server_name": server_name,
        "tool_name": tool_name,
        "arguments": arguments,
        "depends_on": depends_on or [],
    }


# Define the no-LLM planner used for fast local testing.
def plan_with_mock(prompt: str) -> dict:
    # Convert the prompt to lowercase once for keyword checks.
    prompt_lower = prompt.lower()
    # Extract an optional ISO date from the prompt.
    travel_date = extract_date(prompt)
    # Infer a route such as BLR -> DEL from the prompt.
    route = infer_route(prompt)

    # If the user asks about available tools, return a local list-tools action.
    if "tool" in prompt_lower or "what can you" in prompt_lower:
        # Return a plan with one local step.
        return {"steps": [make_step("list_tools", "local", "list_tools", {})]}

    # Decide whether the user is asking for flights.
    wants_flight = "flight" in prompt_lower or "travel" in prompt_lower or "travelling" in prompt_lower
    # Decide whether the user is asking for hotels/stays.
    wants_hotel = "hotel" in prompt_lower or "stay" in prompt_lower or "staying" in prompt_lower

    # Create an empty list of steps.
    steps = []
    # If flight search is requested and a route was found, add a flight step.
    if wants_flight and route:
        # Split the route into origin and destination codes.
        origin, destination = route
        # Build the flight search arguments.
        flight_args = {"origin": origin, "destination": destination}
        # Add a date filter when the user provided one.
        if travel_date:
            # Store the optional flight departure date.
            flight_args["date"] = travel_date
        # Add the flight search step.
        steps.append(make_step("search_flights", "flight", "search_flights", flight_args))

    # If hotel search is requested, add a hotel step.
    if wants_hotel:
        # Pick the destination city from the route when available; otherwise use a known city in the prompt.
        destination_city = (
            AIRPORT_TO_CITY.get(route[1])
            if route
            else next(
                (city.title() for city in CITY_TO_AIRPORT if city in prompt_lower),
                None,
            )
        )
        # If a destination city was found, build a hotel step.
        if destination_city:
            # Build hotel search arguments.
            hotel_args = {"city": destination_city}
            # If the user gave a date, use it as the check-in date.
            if travel_date:
                # Store the optional hotel check-in date.
                hotel_args["check_in_date"] = travel_date
                # Hotel and flight can run in parallel because both arguments are already known.
                depends_on = []
            # If no date was given but there is a flight step, derive the hotel date from the flight result.
            elif any(step["step_id"] == "search_flights" for step in steps):
                # Use a tiny placeholder that the executor resolves after the flight result is available.
                hotel_args["check_in_date"] = "$first_flight_date:search_flights"
                # Make the hotel step wait for the flight search result.
                depends_on = ["search_flights"]
            # If no flight step exists, search hotels without a date.
            else:
                # Run independently because no previous result is needed.
                depends_on = []
            # Add the hotel search step.
            steps.append(make_step("search_hotels", "hotel", "search_hotels", hotel_args, depends_on))

    # If no steps were created, return a final answer explaining the limitation.
    if not steps:
        # Return an empty plan with a human-readable explanation.
        return {
            "steps": [],
            "final_answer": "I need a route or city, for example: Help me travel from Bangalore to Delhi and stay there.",
        }

    # Return the complete executable plan.
    return {"steps": steps}


# Define a helper that extracts a JSON object from an LLM response.
def extract_json_object(text: str) -> dict:
    # Find the first opening brace.
    start = text.find("{")
    # Find the last closing brace.
    end = text.rfind("}")
    # Validate that the response contains a JSON-looking object.
    if start == -1 or end == -1 or end < start:
        # Raise a clear error with the raw model text.
        raise ValueError(f"LLM did not return JSON: {text}")
    # Parse and return the JSON object.
    return json.loads(text[start : end + 1])


# Define one LLM entry point that routes to the selected provider.
def call_llm(instructions: str, input_text: str) -> str:
    # Print the instructions being sent to the selected LLM provider.
    debug_print("LLM instructions", instructions.strip())
    # Print the input payload being sent to the selected LLM provider.
    debug_print("LLM input", input_text)

    # Use Ollama when configured.
    if LLM_PROVIDER == "ollama":
        # Call Ollama and store the raw response text.
        response_text = call_ollama(instructions, input_text)
        # Print the raw Ollama response text.
        debug_print("LLM raw response", response_text)
        # Return the Ollama model output.
        return response_text

    # Use OpenAI when configured.
    if LLM_PROVIDER == "openai":
        # Call OpenAI and store the raw response text.
        response_text = call_openai(instructions, input_text)
        # Print the raw OpenAI response text.
        debug_print("LLM raw response", response_text)
        # Return the OpenAI model output.
        return response_text

    # Reject unknown provider names.
    raise ValueError("LLM_PROVIDER must be one of: ollama, openai, mock")


# Define the provider-specific function that calls Ollama.
def call_ollama(instructions: str, input_text: str) -> str:
    # Start a block that can catch local Ollama setup failures.
    try:
        # Send a non-streaming chat request to Ollama.
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    # Catch the case where Ollama is not running.
    except RequestsConnectionError as exc:
        # Raise a friendlier setup error.
        raise RuntimeError(
            f"Could not connect to Ollama at {OLLAMA_BASE_URL}. "
            f"Start Ollama and run: ollama pull {OLLAMA_MODEL}. "
            "Or use mock mode with: $env:LLM_PROVIDER='mock'"
        ) from exc
    # Catch the case where Ollama is running but too slow.
    except ReadTimeout as exc:
        # Raise a friendlier timeout error.
        raise RuntimeError(
            f"Ollama at {OLLAMA_BASE_URL} did not answer within {OLLAMA_TIMEOUT_SECONDS} seconds. "
            "Try again, increase $env:OLLAMA_TIMEOUT_SECONDS='300', or use llama3.2:1b."
        ) from exc

    # Raise an exception for failed HTTP responses.
    response.raise_for_status()
    # Return the assistant message content.
    return response.json()["message"]["content"]


# Define the provider-specific function that calls OpenAI.
def call_openai(instructions: str, input_text: str) -> str:
    # Import lazily so Ollama/mock users do not need the OpenAI path.
    from openai import OpenAI

    # Create the OpenAI client.
    client = OpenAI()
    # Send the request using the Responses API.
    response = client.responses.create(model=OPENAI_MODEL, instructions=instructions, input=input_text)
    # Return the model's text output.
    return response.output_text


# Define a helper that converts MCP tool metadata to a dictionary.
def server_tool_to_dict(server_name: str, tool) -> dict:
    # Return the server name plus the useful tool metadata.
    return {
        "server_name": server_name,
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


# Define the LLM-powered multi-step planner.
def plan_with_llm(prompt: str, tools: list[dict]) -> dict:
    # Store the instructions for creating an execution plan.
    instructions = """
You are a travel planning agent.
Create an execution plan using the available MCP tools.
Return only valid JSON.

JSON shape:
{
  "steps": [
    {
      "step_id": "short_unique_id",
      "server_name": "flight",
      "tool_name": "search_flights",
      "arguments": {"origin": "BLR", "destination": "DEL", "date": "2026-06-10"},
      "depends_on": []
    }
  ]
}

Rules:
- Use multiple steps when the user asks for multiple kinds of help.
- Use flight tools for flight-related or travel-route requests.
- Use hotel tools for hotel, stay, or accommodation requests.
- If two steps can be done independently, use "depends_on": [] for both.
- If one step needs the result of another step, put the previous step_id in "depends_on".
- Do not invent tool names. Use only the available_tools list.
- Map only known cities: Bangalore/Bengaluru -> BLR, Delhi -> DEL, Mumbai -> BOM, Chennai -> MAA.
- For hotel searches, use the destination city.
- If the user provides a date, pass it to flight as "date" and to hotel as "check_in_date".
- If the user asks for hotel based on the flight date and no date is provided, set hotel "check_in_date" to "$first_flight_date:search_flights" and make it depend on "search_flights".
- If the request is impossible with available tools, return {"steps": [], "final_answer": "Explain what is missing."}.

Parallel example:
User: Help me travel from Bangalore to Delhi on 2026-06-10 and stay there.
Return:
{
  "steps": [
    {"step_id": "search_flights", "server_name": "flight", "tool_name": "search_flights", "arguments": {"origin": "BLR", "destination": "DEL", "date": "2026-06-10"}, "depends_on": []},
    {"step_id": "search_hotels", "server_name": "hotel", "tool_name": "search_hotels", "arguments": {"city": "Delhi", "check_in_date": "2026-06-10"}, "depends_on": []}
  ]
}

Sequential example:
User: Find a flight from Bangalore to Delhi and then find hotels based on when I arrive.
Return:
{
  "steps": [
    {"step_id": "search_flights", "server_name": "flight", "tool_name": "search_flights", "arguments": {"origin": "BLR", "destination": "DEL"}, "depends_on": []},
    {"step_id": "search_hotels", "server_name": "hotel", "tool_name": "search_hotels", "arguments": {"city": "Delhi", "check_in_date": "$first_flight_date:search_flights"}, "depends_on": ["search_flights"]}
  ]
}
"""
    # Build the model input with the user prompt and tool catalog.
    input_text = json.dumps({"user_prompt": prompt, "available_tools": tools}, indent=2)
    # Parse the model's JSON plan.
    plan = extract_json_object(call_llm(instructions, input_text))
    # Print the parsed execution plan.
    debug_print("Parsed execution plan", plan)
    # Return the parsed execution plan.
    return plan


# Define a helper that extracts plain text chunks from an MCP result.
def extract_text_content(tool_result) -> str:
    # Collect text chunks here.
    parts = []
    # Loop through MCP content items.
    for item in tool_result.content:
        # Keep items that expose a text field.
        if hasattr(item, "text"):
            # Add the text to the list.
            parts.append(item.text)

    # FIX: MCP v2 formats list items as multiple pretty-printed TextContent blocks.
    # Reconstruct a valid JSON array if multiple JSON objects are returned.
    if len(parts) > 1 and all(p.strip().startswith("{") and p.strip().endswith("}") for p in parts):
        return "[" + ",\n".join(parts) + "]"

    # Return all text chunks as one string.
    return "\n".join(parts)


# Define a helper that parses MCP text into JSON data.
def parse_tool_json(raw_text: str):
    # Try parsing the full text as JSON first.
    try:
        # Return the parsed JSON value.
        return json.loads(raw_text)
    # Handle line-by-line JSON chunks.
    except json.JSONDecodeError:
        # Parse each non-empty line as JSON.
        return [json.loads(line) for line in raw_text.splitlines() if line.strip()]


# Define a helper that extracts a date from the first flight result.
def first_flight_date(raw_text: str) -> str | None:
    # Parse the flight tool output.
    flights = parse_tool_json(raw_text)
    # Wrap a single flight dictionary in a list.
    if isinstance(flights, dict):
        # Normalize to a list.
        flights = [flights]
    # If there are no flights, there is no date to extract.
    if not flights:
        # Return no date.
        return None
    # Return the YYYY-MM-DD part of the first flight's departure timestamp.
    return flights[0]["departure_time"][:10]


# Define a helper that resolves argument placeholders using previous step results.
def resolve_arguments(arguments: dict, completed: dict) -> dict:
    # Create a new dictionary so the original plan is not modified.
    resolved = {}
    # Loop over every argument in the step.
    for key, value in arguments.items():
        # Check for the special placeholder used by sequential hotel searches.
        if isinstance(value, str) and value.startswith("$first_flight_date:"):
            # Extract the dependency step id after the colon.
            step_id = value.split(":", 1)[1]
            # Look up the previous step's raw result.
            previous_result = completed[step_id]["raw_text"]
            # Resolve the placeholder to the first flight's date.
            resolved[key] = first_flight_date(previous_result)
        # Keep normal argument values unchanged.
        else:
            # Copy the argument value as-is.
            resolved[key] = value
    # Return the resolved argument dictionary.
    return resolved


# Define a helper that formats flight JSON for mock mode.
def format_flights(raw_text: str) -> str:
    # Parse the tool output.
    flights = parse_tool_json(raw_text)
    # Normalize one flight object into a list.
    if isinstance(flights, dict):
        # Wrap the dictionary.
        flights = [flights]
    # Return a no-results message when empty.
    if not flights:
        # No flights were found.
        return "No matching flights."
    # Start the output lines.
    lines = ["Flights:"]
    # Loop over flights.
    for flight in flights:
        # Add one readable flight line.
        lines.append(
            "- {id}: {airline} {flight_number}, {origin}->{destination}, {departure_time}, Rs {price}, seats: {seats_available}".format(
                **flight
            )
        )
    # Return the final formatted block.
    return "\n".join(lines)


# Define a helper that formats hotel JSON for mock mode.
def format_hotels(raw_text: str) -> str:
    # Parse the tool output.
    hotels = parse_tool_json(raw_text)
    # Normalize one hotel object into a list.
    if isinstance(hotels, dict):
        # Wrap the dictionary.
        hotels = [hotels]
    # Return a no-results message when empty.
    if not hotels:
        # No hotels were found.
        return "No matching hotels."
    # Start the output lines.
    lines = ["Hotels:"]
    # Loop over hotels.
    for hotel in hotels:
        # Add one readable hotel line.
        lines.append(
            "- {id}: {name}, {city} ({area}), check-in {check_in_date}, Rs {price_per_night}/night, rooms: {rooms_available}, rating: {rating}".format(
                **hotel
            )
        )
    # Return the final formatted block.
    return "\n".join(lines)


# Define a helper that collects the environment variables the MCP server subprocesses need.
def build_mcp_server_env() -> dict[str, str]:
    # Forward only the configured variables that are actually set in this process.
    return {name: os.environ[name] for name in MCP_FORWARDED_ENV_VARS if name in os.environ}


# Define a helper that connects to every configured MCP server.
async def connect_mcp_servers(stack: AsyncExitStack) -> dict[str, ClientSession]:
    # Store sessions by server name.
    sessions: dict[str, ClientSession] = {}
    # Loop through configured MCP servers.
    for server_name, server_path in MCP_SERVER_PATHS.items():
        # Describe how to launch this MCP server.
        params = StdioServerParameters(command=sys.executable, args=[str(server_path)], env=build_mcp_server_env())
        # Open stdio streams for this server.
        read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
        # Create an MCP client session.
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        # Initialize the MCP session.
        await session.initialize()
        # Store the session.
        sessions[server_name] = session
    # Return all sessions.
    return sessions


# Define a helper that lists tools from all MCP servers.
async def list_all_tools(sessions: dict[str, ClientSession]) -> list[dict]:
    # Store the combined tool catalog.
    catalog = []
    # Loop over every session.
    for server_name, session in sessions.items():
        # Ask this server for its tools.
        tools = await session.list_tools()
        # Add each tool with server ownership.
        catalog.extend(server_tool_to_dict(server_name, tool) for tool in tools.tools)
    # Return the combined catalog.
    return catalog


# Define a helper that runs one plan step.
async def execute_step(step: dict, sessions: dict[str, ClientSession], completed: dict) -> tuple[str, dict]:
    # Read the step id.
    step_id = step["step_id"]
    # Read the selected MCP server name.
    server_name = step["server_name"]
    # Read the selected MCP tool name.
    tool_name = step["tool_name"]
    # Resolve arguments, including any placeholders from previous results.
    arguments = resolve_arguments(step.get("arguments", {}), completed)
    # Print the step that is about to run.
    debug_print(
        "Executing step",
        {"step_id": step_id, "server_name": server_name, "tool_name": tool_name, "arguments": arguments},
    )
    # Reject unknown MCP server names.
    if server_name not in sessions:
        # Raise a clear setup/planning error.
        raise RuntimeError(f"Unknown MCP server selected: {server_name}")
    # Call the selected MCP tool.
    result = await sessions[server_name].call_tool(tool_name, arguments)
    # Extract plain text from the MCP result.
    raw_text = extract_text_content(result)
    # Print the raw MCP tool result for this step.
    debug_print(f"MCP result for {step_id}", raw_text)
    # Return the step id and stored result object.
    return step_id, {"server_name": server_name, "tool_name": tool_name, "arguments": arguments, "raw_text": raw_text}


# Define the plan executor that supports parallel and sequential steps.
async def execute_plan(plan: dict, sessions: dict[str, ClientSession]) -> dict:
    # Read the list of steps from the plan.
    steps = plan.get("steps", [])
    # Store completed step results by step id.
    completed = {}
    # Keep running until every step is complete.
    while len(completed) < len(steps):
        # Find steps whose dependencies are already complete.
        ready_steps = [
            step
            for step in steps
            if step["step_id"] not in completed
            and all(dependency in completed for dependency in step.get("depends_on", []))
        ]
        # Detect a bad plan with circular or missing dependencies.
        if not ready_steps:
            # Raise a clear error explaining that execution cannot continue.
            raise RuntimeError("No executable plan steps are ready. Check depends_on values.")
        # Run all currently ready steps concurrently.
        results = await asyncio.gather(*(execute_step(step, sessions, completed) for step in ready_steps))
        # Store every completed result.
        for step_id, result in results:
            # Save this step result.
            completed[step_id] = result
    # Return all completed step results.
    return completed


# Define the LLM-powered final-answer step for multi-step plans.
def answer_with_llm(prompt: str, plan: dict, step_results: dict) -> str:
    # Store the summarizer instructions.
    instructions = """
You are a helpful travel assistant.
Use the tool results as the source of truth.
Summarize all successful results.
If a step failed or returned no data, explain that clearly.
Do not invent flights, hotels, prices, dates, seats, ratings, or availability.
"""
    # Build the model input.
    input_text = json.dumps({"user_prompt": prompt, "plan": plan, "step_results": step_results}, indent=2)
    # Print the complete data being sent to the final summarizer.
    debug_print("Final summarizer input", input_text)
    # Return the LLM's final response.
    return call_llm(instructions, input_text)


# Define the mock final-answer formatter.
def answer_with_mock(step_results: dict) -> str:
    # Store formatted result sections.
    sections = []
    # Loop over each completed step result.
    for result in step_results.values():
        # Format flight results.
        if result["tool_name"] == "search_flights":
            # Add formatted flights.
            sections.append(format_flights(result["raw_text"]))
        # Format hotel results.
        elif result["tool_name"] == "search_hotels":
            # Add formatted hotels.
            sections.append(format_hotels(result["raw_text"]))
        # Otherwise include raw output.
        else:
            # Add raw result text.
            sections.append(result["raw_text"])
    # Join the sections with spacing.
    return "\n\n".join(sections)


# Define the main asynchronous agent workflow.
async def run_agent(prompt: str) -> str:
    # Use an LLM unless mock mode is explicitly selected.
    use_real_llm = LLM_PROVIDER != "mock"
    # Open all MCP sessions together.
    async with AsyncExitStack() as stack:
        # Connect to every configured MCP server.
        sessions = await connect_mcp_servers(stack)
        # List all available MCP tools.
        available_tools = await list_all_tools(sessions)

        # If the prompt asks for tools, return the combined catalog.
        if "tool" in prompt.lower() or "what can you" in prompt.lower():
            # Return compact server.tool labels.
            return "Available MCP tools: " + ", ".join(
                f"{tool['server_name']}.{tool['name']}" for tool in available_tools
            )

        # Create a multi-step plan with either the LLM or mock planner.
        plan = plan_with_llm(prompt, available_tools) if use_real_llm else plan_with_mock(prompt)
        # Return the planner's final answer when no steps are possible.
        if not plan.get("steps"):
            # Return the final answer from the plan, or a fallback message.
            return plan.get("final_answer", "I could not create an executable plan.")

        # Execute the plan, running independent steps in parallel.
        step_results = await execute_plan(plan, sessions)
        # Summarize with the selected real LLM.
        if use_real_llm:
            # Return the LLM final answer.
            return answer_with_llm(prompt, plan, step_results)
        # Summarize deterministically in mock mode.
        return answer_with_mock(step_results)


# Define a helper that finds friendly RuntimeError objects inside ExceptionGroups.
def find_runtime_error(exc: BaseException) -> RuntimeError | None:
    # Return the error if it is already a RuntimeError.
    if isinstance(exc, RuntimeError):
        # Return this friendly error.
        return exc
    # Search inside Python 3.11 ExceptionGroup values.
    if isinstance(exc, BaseExceptionGroup):
        # Loop through nested exceptions.
        for nested_exc in exc.exceptions:
            # Search recursively.
            runtime_error = find_runtime_error(nested_exc)
            # Return the first friendly error found.
            if runtime_error is not None:
                # Return the found error.
                return runtime_error
    # Return None when no friendly error exists.
    return None


# Define the command-line entry point.
def main() -> None:
    # Combine command-line words into one prompt.
    prompt = " ".join(sys.argv[1:]).strip()
    # Ask interactively when no prompt was supplied.
    if not prompt:
        # Read the prompt from the terminal.
        prompt = input("Ask about travel: ").strip()

    # Run the async agent workflow and catch friendly setup errors.
    try:
        # Execute the agent.
        response = asyncio.run(run_agent(prompt))
    # Catch all exceptions so ExceptionGroups can be unwrapped.
    except BaseException as exc:
        # Try to find a friendly RuntimeError.
        runtime_error = find_runtime_error(exc)
        # Re-raise unexpected bugs.
        if runtime_error is None:
            # Re-raise the original exception.
            raise
        # Print the friendly setup/planning error.
        print(f"Setup error: {runtime_error}")
        # Exit with a failure status code.
        sys.exit(1)

    # Print the final response.
    print(response)


# Run the CLI only when this file is executed directly.
if __name__ == "__main__":
    # Start the command-line program.
    main()
