"""
Unit tests for AIGenerator tool-calling flow.

All tests mock the Anthropic client — no real API calls are made.

Expected failures (revealing bugs):
- test_no_tool_manager_skips_tool_execution: PASSES with pytest.raises(AttributeError) —
  confirms the latent bug where tool_use response + tool_manager=None causes AttributeError
  when the code falls through to response.content[0].text on a tool_use block.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, call
from ai_generator import AIGenerator
from search_tools import ToolManager


def make_end_turn_response(text: str) -> MagicMock:
    """Build a mock Anthropic response simulating stop_reason='end_turn'."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [content_block]
    return response


def make_tool_use_response(tool_name: str, tool_id: str, tool_input: dict) -> MagicMock:
    """Build a mock Anthropic response simulating stop_reason='tool_use'."""
    content_block = MagicMock()
    content_block.type = "tool_use"
    content_block.name = tool_name
    content_block.id = tool_id
    content_block.input = tool_input

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [content_block]
    return response


@pytest.fixture
def mock_tool_manager():
    """A ToolManager with a mocked execute_tool that returns 'search results text'."""
    tm = MagicMock(spec=ToolManager)
    tm.execute_tool.return_value = "search results text"
    return tm


class TestEndTurnPath:
    def test_end_turn_returns_text_directly(self):
        """When stop_reason='end_turn', generate_response() returns content[0].text
        and messages.create is called exactly once (no tool execution)."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = make_end_turn_response("Direct answer here")

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            result = ai.generate_response(query="What is Python?")

        assert result == "Direct answer here"
        assert mock_client.messages.create.call_count == 1

    def test_end_turn_with_no_tools_provided(self):
        """When no tools are passed, the API call should not include tools or tool_choice keys."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = make_end_turn_response("Answer")

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(query="Hello", tools=None)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    def test_end_turn_with_conversation_history(self):
        """Conversation history is injected into the system prompt, not as messages."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = make_end_turn_response("Answer")

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(query="Follow-up question", conversation_history="User: Hi\nAssistant: Hello")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "Previous conversation" in call_kwargs["system"]
        assert "User: Hi" in call_kwargs["system"]
        # History should NOT appear as a separate message, only in system
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"


class TestToolUsePath:
    def test_tool_use_triggers_two_api_calls(self, mock_tool_manager):
        """When stop_reason='tool_use', generate_response() makes exactly 2 API calls:
        one to get the tool request, one to synthesize after tool execution."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = [
                make_tool_use_response("search_course_content", "tu_001", {"query": "Python loops"}),
                make_end_turn_response("Synthesized answer"),
            ]

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            result = ai.generate_response(
                query="Tell me about Python loops",
                tools=[{"name": "search_course_content", "description": "...", "input_schema": {}}],
                tool_manager=mock_tool_manager,
            )

        assert result == "Synthesized answer"
        assert mock_client.messages.create.call_count == 2

    def test_tool_use_calls_execute_tool_with_correct_kwargs(self, mock_tool_manager):
        """_handle_tool_execution unpacks content_block.input as **kwargs to execute_tool.
        Verifies the tool name and all input fields are passed correctly."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = [
                make_tool_use_response(
                    "search_course_content",
                    "tu_002",
                    {"query": "recursion", "lesson_number": 3},
                ),
                make_end_turn_response("Final answer"),
            ]

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(
                query="Explain recursion in lesson 3",
                tools=[],
                tool_manager=mock_tool_manager,
            )

        mock_tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="recursion", lesson_number=3
        )

    def test_intermediate_call_includes_tools_when_tools_provided(self, mock_tool_manager):
        """In a 1-round flow (tool_use → end_turn), call #2 is an intermediate round
        (round_idx=0 < MAX_TOOL_ROUNDS-1), so it INCLUDES tools and tool_choice.
        This allows Claude to decide whether to chain a second search."""
        tools = [{"name": "search_course_content"}]
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = [
                make_tool_use_response("search_course_content", "tu_003", {"query": "variables"}),
                make_end_turn_response("Answer"),
            ]

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(
                query="Explain variables",
                tools=tools,
                tool_manager=mock_tool_manager,
            )

        second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
        assert "tools" in second_call_kwargs
        assert "tool_choice" in second_call_kwargs

    def test_messages_structure_in_second_api_call(self, mock_tool_manager):
        """The second API call's messages must contain:
        [0] original user message
        [1] assistant message with tool_use content blocks
        [2] user message with tool_result content
        """
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            tool_use_response = make_tool_use_response(
                "search_course_content", "tu_004", {"query": "functions"}
            )
            mock_client.messages.create.side_effect = [
                tool_use_response,
                make_end_turn_response("Final"),
            ]

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(
                query="Explain functions",
                tools=[],
                tool_manager=mock_tool_manager,
            )

        second_call_messages = mock_client.messages.create.call_args_list[1].kwargs["messages"]

        assert len(second_call_messages) == 3
        assert second_call_messages[0]["role"] == "user"
        assert second_call_messages[1]["role"] == "assistant"
        assert second_call_messages[1]["content"] == tool_use_response.content
        assert second_call_messages[2]["role"] == "user"

    def test_tool_result_dict_structure(self, mock_tool_manager):
        """The tool result dict in the 3rd message must have exactly:
        {type: 'tool_result', tool_use_id: <id>, content: <string>}
        Any deviation causes Anthropic API 400 errors."""
        mock_tool_manager.execute_tool.return_value = "the search output"

        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = [
                make_tool_use_response("search_course_content", "abc123", {"query": "loops"}),
                make_end_turn_response("Done"),
            ]

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(query="Loops", tools=[], tool_manager=mock_tool_manager)

        third_message = mock_client.messages.create.call_args_list[1].kwargs["messages"][2]
        tool_result = third_message["content"][0]

        assert tool_result["type"] == "tool_result"
        assert tool_result["tool_use_id"] == "abc123"
        assert tool_result["content"] == "the search output"


class TestEdgeCases:
    def test_no_tool_manager_with_tool_use_response_returns_empty(self):
        """FIXED: When stop_reason='tool_use' but tool_manager=None, the code used to
        fall through to response.content[0].text (a ToolUseBlock with no .text) →
        AttributeError. After the fix, it returns "" gracefully instead.

        The mock uses spec=['type', 'name', 'id', 'input'] (no 'text') to simulate
        a real ToolUseBlock. Without spec, MagicMock auto-creates .text."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value

            # Restrict mock attributes to simulate a real ToolUseBlock (no .text)
            content_block = MagicMock(spec=["type", "name", "id", "input"])
            content_block.type = "tool_use"
            content_block.name = "search_course_content"
            content_block.id = "tu_err"
            content_block.input = {"query": "test"}

            response = MagicMock()
            response.stop_reason = "tool_use"
            response.content = [content_block]
            mock_client.messages.create.return_value = response

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")

            result = ai.generate_response(
                query="Content question",
                tools=[{"name": "search_course_content"}],
                tool_manager=None,
            )

            assert result == ""

    def test_tools_list_passed_to_first_api_call(self, mock_tool_manager):
        """When tools are provided, the first API call must include both
        'tools' and 'tool_choice' keys."""
        tools = [{"name": "search_course_content", "description": "...", "input_schema": {}}]

        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = make_end_turn_response("Direct answer")

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(query="Question", tools=tools, tool_manager=mock_tool_manager)

        first_call_kwargs = mock_client.messages.create.call_args_list[0].kwargs
        assert "tools" in first_call_kwargs
        assert first_call_kwargs["tools"] == tools
        assert "tool_choice" in first_call_kwargs
        assert first_call_kwargs["tool_choice"] == {"type": "auto"}


class TestTwoRoundToolCallPath:
    """Tests for the 2-round sequential tool-calling flow (3 total API calls)."""

    def _make_side_effect(self):
        """Return side_effect list: [tool_use_r1, tool_use_r2, end_turn]."""
        return [
            make_tool_use_response("search_course_content", "tu_r1", {"query": "outline"}),
            make_tool_use_response("search_course_content", "tu_r2", {"query": "topic"}),
            make_end_turn_response("Final synthesized answer"),
        ]

    def _run(self, mock_client, mock_tool_manager, tools=None):
        if tools is None:
            tools = [{"name": "search_course_content", "description": "...", "input_schema": {}}]
        ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
        return ai.generate_response(
            query="Complex query",
            tools=tools,
            tool_manager=mock_tool_manager,
        )

    def test_two_rounds_makes_three_api_calls(self, mock_tool_manager):
        """2 sequential tool uses + 1 synthesis = 3 API calls total."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = self._make_side_effect()

            result = self._run(mock_client, mock_tool_manager)

        assert mock_client.messages.create.call_count == 3
        assert result == "Final synthesized answer"

    def test_second_round_intermediate_call_includes_tools(self, mock_tool_manager):
        """Call #2 (round_idx=0, not last) must include tools so Claude can chain."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = self._make_side_effect()

            self._run(mock_client, mock_tool_manager)

        second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
        assert "tools" in second_call_kwargs

    def test_third_call_synthesis_excludes_tools(self, mock_tool_manager):
        """Call #3 (last round, synthesis) must NOT include tools or tool_choice."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = self._make_side_effect()

            self._run(mock_client, mock_tool_manager)

        third_call_kwargs = mock_client.messages.create.call_args_list[2].kwargs
        assert "tools" not in third_call_kwargs
        assert "tool_choice" not in third_call_kwargs

    def test_two_rounds_execute_tool_called_twice(self, mock_tool_manager):
        """execute_tool must be called once per round with the correct tool name and args."""
        mock_tool_manager.execute_tool.return_value = "results"
        side_effect = [
            make_tool_use_response("get_course_outline", "tu_r1", {"course": "Python 101"}),
            make_tool_use_response("search_course_content", "tu_r2", {"query": "loops"}),
            make_end_turn_response("Done"),
        ]
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = side_effect

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            ai.generate_response(
                query="Find loops in Python 101",
                tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
                tool_manager=mock_tool_manager,
            )

        assert mock_tool_manager.execute_tool.call_count == 2
        mock_tool_manager.execute_tool.assert_any_call("get_course_outline", course="Python 101")
        mock_tool_manager.execute_tool.assert_any_call("search_course_content", query="loops")

    def test_two_rounds_messages_structure(self, mock_tool_manager):
        """Call #3 messages must contain 5 entries:
        [0] user query
        [1] assistant tool_use round 1
        [2] user tool_results round 1
        [3] assistant tool_use round 2
        [4] user tool_results round 2
        """
        side_effect = self._make_side_effect()
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.side_effect = side_effect

            self._run(mock_client, mock_tool_manager)

        third_call_messages = mock_client.messages.create.call_args_list[2].kwargs["messages"]
        assert len(third_call_messages) == 5
        assert third_call_messages[0]["role"] == "user"
        assert third_call_messages[1]["role"] == "assistant"
        assert third_call_messages[2]["role"] == "user"
        assert third_call_messages[3]["role"] == "assistant"
        assert third_call_messages[4]["role"] == "user"

    def test_tool_error_terminates_loop_gracefully(self, mock_tool_manager):
        """If execute_tool raises an exception, the loop breaks and "" is returned."""
        mock_tool_manager.execute_tool.side_effect = Exception("search failed")

        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = make_tool_use_response(
                "search_course_content", "tu_err", {"query": "error case"}
            )

            ai = AIGenerator(api_key="fake", model="claude-sonnet-4-20250514")
            result = ai.generate_response(
                query="Trigger error",
                tools=[{"name": "search_course_content"}],
                tool_manager=mock_tool_manager,
            )

        assert result == ""
