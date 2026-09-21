# LiveKit Flows

[![PyPI version](https://img.shields.io/pypi/v/livekit-flows)](https://pypi.org/project/livekit-flows/)

A Python library for building declarative, flow-based conversational AI agents with [LiveKit](https://livekit.io/).

LiveKit Flows allows you to define complex conversation flows using simple Python code or YAML files, making it easy to build structured voice agents that guide users through multi-step interactions.

## Features

- 🎯 **Declarative Flow Definition** - Define conversation flows using Python or YAML
- 🔄 **State Management** - Built-in flow state tracking and transitions
- 🎤 **Voice-First** - Seamlessly integrates with LiveKit's real-time audio/video
- 🔌 **HTTP Actions** - Execute HTTP requests during conversation flows
- 📊 **Data Collection** - Collect and validate structured data from conversations
- 🎨 **Visual Editor** - Interactive web-based flow editor

## Installation

Install from PyPI using your preferred package manager:

### pip
```bash
pip install livekit-flows
```

### uv
```bash
uv add livekit-flows
```

### Poetry
```bash
poetry add livekit-flows
```

### Development Installation

```bash
git clone https://github.com/mateuszkulpa/livekit-flows.git
cd livekit-flows
uv sync
```

## Quick Start

Here's a minimal example of a restaurant reservation agent:

```python
from livekit.agents import AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import openai, cartesia, deepgram, silero
from livekit_flows import FlowAgent, ConversationFlow, FlowNode, Edge

# Define the conversation flow
reservation_flow = ConversationFlow(
    system_prompt="You are a friendly restaurant reservation assistant.",
    initial_node="welcome",
    nodes=[
        FlowNode(
            id="welcome",
            name="Welcome",
            static_text="Hi! I'll help you make a reservation. What's your name?",
            edges=[
                Edge(
                    condition="Got name",
                    id="to_details",
                    target_node_id="get_details",
                )
            ],
        ),
        FlowNode(
            id="get_details",
            name="Get Details",
            instruction="Ask about party size, date, and time.",
            edges=[
                Edge(
                    condition="Got all details",
                    id="to_confirm",
                    target_node_id="confirm",
                )
            ],
        ),
        FlowNode(
            id="confirm",
            name="Confirm",
            instruction="Confirm all reservation details with the user.",
            edges=[
                Edge(condition="Confirmed", id="to_done", target_node_id="done"),
                Edge(
                    condition="Need changes",
                    id="to_details",
                    target_node_id="get_details",
                ),
            ],
        ),
        FlowNode(
            id="done",
            name="Done",
            static_text="Perfect! Your reservation is confirmed. See you then!",
            is_final=True,
        ),
    ],
)


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    agent = FlowAgent(flow=reservation_flow)
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=cartesia.TTS(),
    )

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

## YAML Configuration

You can also define flows using YAML for better readability and easier editing:

```yaml
system_prompt: "You are a friendly restaurant reservation assistant."

initial_node: "welcome"

nodes:
  - id: "welcome"
    name: "Welcome"
    static_text: "Hi! I'll help you make a reservation. What's your name?"
    edges:
      - condition: "Got name"
        id: "to_details"
        target_node_id: "get_details"

  - id: "get_details"
    name: "Get Details"
    instruction: "Ask about party size, date, and time."
    edges:
      - condition: "Got all details"
        id: "to_confirm"
        target_node_id: "confirm"

  - id: "confirm"
    name: "Confirm"
    instruction: "Confirm all reservation details with the user."
    edges:
      - condition: "Confirmed"
        id: "to_done"
        target_node_id: "done"
      - condition: "Need changes"
        id: "to_details"
        target_node_id: "get_details"

  - id: "done"
    name: "Done"
    static_text: "Perfect! Your reservation is confirmed. See you then!"
    is_final: true
```

Load the YAML flow in your Python code:

```python
from livekit_flows import ConversationFlow

flow = ConversationFlow.from_yaml_file("path/to/flow.yaml")
agent = FlowAgent(flow=flow)
```

## HTTP Actions

Execute HTTP requests during your flows with built-in action support:

```yaml
actions:
  - id: "get_cat_fact"
    name: "Get Cat Fact"
    description: "Fetches a random cat fact"
    method: "GET"
    url: "https://catfact.ninja/fact"
    store_response_as: "cat_fact"

nodes:
  - id: "share_fact"
    name: "Share Fact"
    instruction: |
      Share this fact with the user:
      {% if actions.cat_fact and actions.cat_fact.success %}
      {{ actions.cat_fact.data.fact }}
      {% endif %}
    actions:
      - trigger_type: "on_enter"
        action_id: "get_cat_fact"
```

## Core Concepts

### FlowNode
A node represents a state in your conversation. Each node can have:
- **static_text**: Fixed text to speak to the user
- **instruction**: Dynamic instructions for the LLM
- **edges**: Conditions for transitioning to other nodes
- **actions**: HTTP actions to execute when entering the node

### Edge
An edge defines a transition between nodes based on:
- **condition**: Natural language condition evaluated by the LLM
- **target_node_id**: The destination node
- **input_schema**: Optional JSON schema for data validation

### CustomAction
HTTP actions that can be triggered during the flow:
- Supports GET, POST, PUT, DELETE, PATCH methods
- Template-based request bodies with Jinja2
- Automatic response storage for use in subsequent nodes

## Visual Editor

This project includes a web-based visual editor for designing flows:

```bash
cd editor
pnpm install
pnpm dev
```

Open http://localhost:3000 to design flows visually and export them as YAML or Python code.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Links

- [GitHub Repository](https://github.com/mateuszkulpa/livekit-flows)
- [LiveKit Documentation](https://docs.livekit.io/)
- [LiveKit Agents Framework](https://github.com/livekit/agents)
