import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use **get_course_outline** for questions about a course's structure, outline, lesson list, or available topics
- Use **search_course_content** for questions about specific content, concepts, or details within lessons
- Up to 2 sequential searches are allowed when a second search depends on results from the first (e.g., get a course outline, then search for a specific topic within it)
- Use a second search only when necessary — prefer answering with a single search
- Synthesize search results into accurate, fact-based responses
- If search yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **Course outline queries**: Use get_course_outline, then present the course title, course link as a markdown hyperlink `[Course Link](url)`, and each lesson as "Lesson N: <title>"
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    MAX_TOOL_ROUNDS = 2

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.
        
        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            
        Returns:
            Generated response as string
        """
        
        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history 
            else self.SYSTEM_PROMPT
        )
        
        # Prepare API call parameters efficiently
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }
        
        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
        
        # Get response from Claude
        response = self.client.messages.create(**api_params)
        
        # Handle tool execution if needed
        if response.stop_reason == "tool_use":
            if tool_manager:
                return self._handle_tool_execution(response, api_params, tool_manager)
            # Tool use requested but no manager available — return empty rather than AttributeError
            return ""

        # Return direct response
        return response.content[0].text
    
    def _handle_tool_execution(self, initial_response, base_params: Dict[str, Any], tool_manager):
        """
        Handle execution of tool calls and get follow-up response.
        Supports up to MAX_TOOL_ROUNDS sequential tool-use rounds before a final synthesis call.

        Args:
            initial_response: The response containing tool use requests
            base_params: Base API parameters
            tool_manager: Manager to execute tools

        Returns:
            Final response text after tool execution, or "" on error
        """
        messages = base_params["messages"].copy()
        current_response = initial_response

        for round_idx in range(self.MAX_TOOL_ROUNDS):
            # Append assistant tool_use content to conversation
            messages.append({"role": "assistant", "content": current_response.content})

            # Execute all tool calls; break on unhandled exception
            tool_results = []
            try:
                for block in current_response.content:
                    if block.type == "tool_use":
                        result = tool_manager.execute_tool(block.name, **block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
            except Exception:
                break  # terminate on error, fall through to return ""

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            is_last_round = (round_idx == self.MAX_TOOL_ROUNDS - 1)

            # Include tools in intermediate rounds so Claude can chain; strip on last round
            call_params = {**self.base_params, "messages": messages, "system": base_params["system"]}
            if not is_last_round and "tools" in base_params:
                call_params["tools"] = base_params["tools"]
                call_params["tool_choice"] = base_params.get("tool_choice", {"type": "auto"})

            response = self.client.messages.create(**call_params)

            if response.stop_reason != "tool_use":
                return response.content[0].text

            # stop_reason is still "tool_use" on last round (tools stripped, shouldn't happen) → return anyway
            if is_last_round:
                return response.content[0].text

            current_response = response  # carry forward for next round

        return ""  # fallback: exception caused early break