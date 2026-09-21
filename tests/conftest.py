from unittest.mock import patch

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def mock_job_context():
    with patch("livekit_flows.agent.session.get_job_context", return_value=None):
        yield
