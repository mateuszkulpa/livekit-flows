import pytest
from aiohttp.web import Application, Response, json_response
from pydantic import BaseModel

from livekit_flows import CustomAction, HttpMethod
from livekit_flows.actions.executor import ActionExecutor
from livekit_flows.templates.renderer import TemplateRenderer


class Guest(BaseModel):
    name: str
    party_size: int


def test_template_renderer_uses_userdata_env_and_action_results():
    renderer = TemplateRenderer()
    rendered = renderer.render_with_data(
        "Hi {{ userdata.name }}, party of {{ userdata.party_size }}. "
        "Token {{ env.token }}. Order {{ actions.order.data.id }}.",
        userdata=Guest(name="Ada", party_size=2),
        environment_vars={"token": "secret"},
        action_results={"order": {"data": {"id": "42"}}},
    )

    assert rendered == "Hi Ada, party of 2. Token secret. Order 42."


def test_template_renderer_returns_original_text_when_template_is_invalid():
    renderer = TemplateRenderer()

    assert renderer.render("Hello {{ userdata.name", {}) == "Hello {{ userdata.name"


def test_template_renderer_applies_custom_context():
    renderer = TemplateRenderer()
    context = renderer.build_context(custom_context={"userdata": {"name": "Grace"}})

    assert renderer.render("{{ userdata.name }}", context) == "Grace"


@pytest.mark.asyncio
async def test_action_executor_renders_request_and_stores_json_response(aiohttp_server):
    seen = {}

    async def create_profile(request):
        seen["method"] = request.method
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = await request.json()
        return json_response({"id": "profile-1"}, status=201)

    app = Application()
    app.router.add_post("/profiles", create_profile)
    server = await aiohttp_server(app)

    action = CustomAction(
        id="create_profile",
        name="Create profile",
        description="Create a guest profile",
        method=HttpMethod.POST,
        url=f"http://{server.host}:{server.port}/profiles",
        headers={"Authorization": "Bearer {{ env.token }}"},
        body_template='{"name": "{{ userdata.name }}", "party_size": {{ userdata.party_size }}}',
        store_response_as="profile",
    )
    executor = ActionExecutor(actions=[action], environment_vars={"token": "secret"})

    async with executor:
        result = await executor.execute_action(
            "create_profile", Guest(name="Ada", party_size=2)
        )

    assert seen == {
        "method": "POST",
        "authorization": "Bearer secret",
        "body": {"name": "Ada", "party_size": 2},
    }
    assert result["success"] is True
    assert result["status"] == 201
    assert result["data"] == {"id": "profile-1"}
    assert executor.action_results["profile"]["data"]["id"] == "profile-1"


@pytest.mark.asyncio
async def test_action_executor_sends_non_json_body_and_reads_text(aiohttp_server):
    seen = {}

    async def echo(request):
        seen["body"] = await request.text()
        return Response(text="plain-ok", status=200)

    app = Application()
    app.router.add_put("/echo", echo)
    server = await aiohttp_server(app)

    action = CustomAction(
        id="echo",
        name="Echo",
        description="Send a raw body",
        method=HttpMethod.PUT,
        url=f"http://{server.host}:{server.port}/echo",
        body_template="name={{ userdata.name }}",
    )

    async with ActionExecutor(actions=[action]) as executor:
        result = await executor.execute_action("echo", Guest(name="Ada", party_size=1))

    assert seen["body"] == "name=Ada"
    assert result["success"] is True
    assert result["data"] == "plain-ok"


@pytest.mark.asyncio
async def test_action_executor_reports_http_errors_missing_actions_and_closed_session(
    aiohttp_server,
):
    async def missing(_request):
        return json_response({"error": "no"}, status=404)

    app = Application()
    app.router.add_get("/missing", missing)
    server = await aiohttp_server(app)
    action = CustomAction(
        id="lookup",
        name="Lookup",
        description="Lookup a record",
        method=HttpMethod.GET,
        url=f"http://{server.host}:{server.port}/missing",
        store_response_as="lookup",
    )
    executor = ActionExecutor(actions=[action])

    assert await executor.execute_action("unknown") == {}

    closed = await executor.execute_action("lookup")
    assert closed["success"] is False
    assert closed["status"] == 500
    assert "HTTP session not initialized" in closed["error"]
    assert executor.action_results["lookup"]["success"] is False

    async with executor:
        not_found = await executor.execute_action("lookup")

    assert not_found["success"] is False
    assert not_found["status"] == 404
    assert not_found["data"] == {"error": "no"}
