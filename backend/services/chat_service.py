"""
ChatService — business logic layer for all chat and code operations.

Routes, controllers, and WebSocket handlers should call this layer,
never the LLM client or copilot engine directly.
"""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Optional, List, Dict, Any

from copilot.conversation_manager import conversation_manager
from copilot.prompt_builder import prompt_builder
from copilot.tool_selector import tool_selector
from services.mcp_host import mcp_host
from llm_client import llm_client

logger = logging.getLogger(__name__)


class ChatService:
    async def process_message(
        self,
        message: str,
        *,
        session_id: str = "default",
        history: List[Dict[str, Any]] = None,
        context_code: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[Any, None]:
        """
        Full chat pipeline: build prompt → stream LLM → detect/execute tools → follow-up.
        """
        yield ""
        
        # Build tool list from MCP Host (Standardized for LLM)
        tools_list = await mcp_host.get_combined_tools()
        system = await prompt_builder.build_system_prompt(query=message)
        
        # Inject the specialized tool section if needed, though PromptBuilder usually handles it.
        # For multi-server, we ensure the system prompt reflects the NEW host discovery.
        messages = [{"role": "system", "content": system}]

        persisted = conversation_manager.get_history(session_id)
        if persisted:
            # Skip the old system prompt if it exists (at index 0)
            if persisted[0]["role"] == "system":
                messages.extend(persisted[1:])
            else:
                messages.extend(persisted)
        elif history:
            # If front-end passed history, also skip its system prompt if it has one
            if history[0]["role"] == "system":
                messages.extend(history[1:])
            else:
                messages.extend(history)

        user_content = prompt_builder.build_user_message(
            message,
            context_code=context_code,
            language=language,
        )

        # Heuristic: If keywords suggest a project/complex task, append decomposition mandate
        complex_keywords = ["project", "build", "create app", "todo app", "resume builder", "structure"]
        if any(kw in message.lower() for kw in complex_keywords):
            user_content += prompt_builder.build_task_decomposition_prompt(message)

        messages.append({"role": "user", "content": user_content})
        conversation_manager.append(session_id, "user", user_content)

        async for chunk in self._run_reasoning_loop(messages, session_id):
            yield chunk

    async def _run_reasoning_loop(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = "default",
    ) -> AsyncGenerator[Any, None]:
        """
        Executes the LLM-Tool-Result loop until completion or max turns.
        """
        from config import config
        max_turns = config.MAX_TURNS
        current_turn = 0
        
        # Local state for loop detection (prevents cross-session interference)
        last_tool_ids = None
        loop_count = 0
        consecutive_error_count = 0
        
        # Per-tool-name call counter: track how many times each tool is called
        # This catches repetition even when parameters change slightly
        tool_call_counts: Dict[str, int] = {}
        
        # Roaming loop detection: track recent parameter sets
        # If we see many variations of the same tool in 10 actions, warn the model
        recent_calls: List[Dict[str, Any]] = []
        # Removed roaming_loop_warned set as per user request to stop warnings.
        
        # File read tracker to detect thrashing (repeatedly reading the same files)
        read_file_history: Dict[str, int] = {}
        
        # Finding Tracker: Force reporting if too many turns pass without one
        turns_since_last_finding = 0
        finding_enforcement_active = False
        
        # GUI tools that need non-visual verification after usage
        GUI_TOOLS = {"type_text", "press_key", "hotkey", "move_and_click", "open_app"}

        # Set task name for clearer logging in StreamingResponse
        try:
            asyncio.current_task().set_name(f"ReasoningLoop-{session_id}")
        except Exception: pass

        try:
            while current_turn < max_turns:
                current_turn += 1
                logger.info("chat_service.reasoning_turn", extra={"turn": current_turn, "session_id": session_id})
                
                # Fresh system prompt (includes tools and workspace context)
                system = await prompt_builder.build_system_prompt()
                
                # Fetch history with room for system prompt
                persisted = conversation_manager.get_history(session_id, reserved_chars=len(system) + 1000)
                
                # Re-inject RAG results in every turn to ensure persistence
                # Find the first ACTUAL user message for the query
                initial_query = ""
                for m in persisted:
                    if m["role"] == "user" and "Tool execution results" not in m["content"]:
                        initial_query = m["content"]
                        break
                
                rag_context = ""
                if initial_query:
                    from services.embedding_service import embedding_service
                    try:
                        semantic_results = await embedding_service.search(initial_query, top_k=5)
                        if semantic_results:
                            found_paths = [res['path'] for res in semantic_results]
                            logger.info(f"chat_service.rag_results | Found {len(found_paths)} relevant snippets in: {found_paths}")
                            
                            rag_context = "\n[RELEVANT CONTEXT FROM EMBEDDINGS]:\n"
                            for res in semantic_results:
                                rag_context += f"• File: {res['path']} (Snippet): {res['snippet'][:500]}\n"
                        else:
                            rag_context = "\n[SYSTEM ADVISORY]: Semantic search (RAG) returned NO relevant snippets. You may need to use 'index_workspace' or manually explore the file structure with 'list_files' and 'scan_directory'.\n"
                    except Exception as e:
                        logger.error(f"chat_service.rag_error | {str(e)}")
                        rag_context = f"\n[SYSTEM WARNING]: RAG search failed: {str(e)}\n"
                
                messages = [{"role": "system", "content": system + rag_context}]
                
                # Skip the old system prompt in persisted history to avoid duplication
                if persisted and persisted[0]["role"] == "system":
                    messages.extend(persisted[1:])
                else:
                    messages.extend(persisted)
                
                # Injection: Turn Pressure (Enforce findings after 10 turns to allow deep analysis)
                if turns_since_last_finding >= 5:
                    pressure_msg = (
                        f"💡 **Knowledge Checkpoint**: You have performed {turns_since_last_finding} turns without recording a discovery. "
                        "Please use `record_finding` soon to share what you've learned so far (minor or major details). "
                        "Your exploration is not blocked, but stay focused on reporting progress."
                    )
                    messages.append({"role": "system", "content": pressure_msg})
                    if not finding_enforcement_active:
                        logger.info(f"Enforcing discovery checkpoint (Turn {current_turn})")
                        finding_enforcement_active = True
                
                # Context Size check (approx)
                total_chars = sum(len(str(m.get('content', ''))) for m in messages)
                logger.info("chat_service.context", extra={"size_chars": total_chars, "messages_count": len(messages)})
                
                full_response = ""
                chunk_count = 0
                
                buffer = ""
                is_inside_tool = False

                async for chunk in llm_client.stream_chat(messages):
                    full_response += chunk
                    buffer += chunk
                    chunk_count += 1
                    
                    if chunk_count % 100 == 0:
                        logger.debug("chat_service.streaming", extra={"chunks": chunk_count, "char_len": len(full_response)})
                    
                    while True:
                        if not is_inside_tool:
                            if "<tool" in buffer:
                                tag_start = buffer.find("<tool")
                                if tag_start > 0:
                                    yield buffer[:tag_start]
                                buffer = buffer[tag_start:]
                                is_inside_tool = True
                                yield {"type": "granular_status", "label": "Capturing Tool", "detail": "Receiving tool parameters..."}
                            else:
                                if len(buffer) > 5:
                                    yield buffer[:-5]
                                    buffer = buffer[-5:]
                                break
                        else:
                            if "</tool>" in buffer:
                                tag_end = buffer.find("</tool>") + len("</tool>")
                                buffer = buffer[tag_end:]
                                is_inside_tool = False
                            else:
                                break
                
                if buffer:
                    yield buffer

                conversation_manager.append(session_id, "assistant", full_response)
                messages.append({"role": "assistant", "content": full_response})

                # If this is the first turn and the assistant provided a plan, mark it
                if current_turn == 1:
                    yield {"type": "granular_status", "label": "Planning", "detail": "Formulating architectural plan..."}

                tool_calls = tool_selector.extract_tool_calls(full_response)
                if not tool_calls:
                    # Check if tags were present but parsing failed
                    if "<tool" in full_response:
                        msg = "Tool tags detected but JSON parsing failed. Please ensure your tool call is VALID JSON inside <tool> tags. Verify parameters and quotes."
                        yield f"\n\n⚠️ **System Notice**: {msg}"
                        messages.append({"role": "system", "content": f"CRITICAL ERROR: {msg}"})
                        yield {"type": "tool_followup_start"}
                        continue
                    break

                yield {"type": "tool_start", "count": len(tool_calls)}
                
                tool_ids = [f"{t.get('name')}:{json.dumps(t.get('parameters'))}" for t in tool_calls]
                logger.info("chat_service.tool_requested", extra={"session_id": session_id, "count": len(tool_calls), "tools": tool_ids})
                
                # Check for loops using local state
                if last_tool_ids == tool_ids:
                    if loop_count >= 1:
                        yield "\n\n⚠️ **System Notice**: Persistent reasoning loop detected. Stopping."
                        break
                    
                    loop_count += 1
                    msg = "Reasoning loop detected. Please try a DIFFERENT parameter or a DIFFERENT tool."
                    yield f"\n\n⚠️ **System Notice**: {msg}"
                    messages.append({"role": "system", "content": f"CRITICAL: {msg}"})
                    # Do NOT increment current_turn here, we want to retry the SAME turn with the loop warning
                    yield {"type": "tool_followup_start"}
                    continue
                else:
                    last_tool_ids = tool_ids
                    loop_count = 0
                
                first_tool = tool_calls[0].get("name", "unknown")
                
                # Active Enforcement: If we are over the turn limit without a finding, 
                # block any tool that isn't record_finding. 
                if turns_since_last_finding >= 7 and first_tool != "record_finding":
                    msg = (
                        f"RESEARCH ADVISORY: You have performed {turns_since_last_finding} actions without writing a report. "
                        "It is HIGHLY RECOMMENDED to use `record_finding` now to summarize your progress. "
                        "Continuing without reporting may lead to turn exhaustion."
                    )
                    yield f"\n\n⚠️ **System Notice**: {msg}"
                    messages.append({"role": "system", "content": f"ADVISORY: {msg}"})
                    # Persist it so the LLM sees it in the next turn
                    conversation_manager.append(session_id, "system", f"ADVISORY: {msg}")
                    # DO NOT BREAK - as per user request (don't block it)

                yield {"type": "granular_status", "label": "Executing Tool", "detail": f"Running {first_tool}..."}

                # Update per-tool call count
                gui_tools_used_this_turn = set()
                for call in tool_calls:
                    tname = call.get("name", "")
                    tparams = call.get("parameters", {})
                    
                    tool_call_counts[tname] = tool_call_counts.get(tname, 0) + 1
                    
                    # 1. Detect Roaming Loops (sliding window of 10 actions)
                    recent_calls.append({"name": tname, "params": tparams})
                    if len(recent_calls) > 10: recent_calls.pop(0)

                    # 2. Detect File Thrashing (specifically for read_file)
                    if tname == "read_file":
                        fpath = tparams.get("path", "")
                        read_file_history[fpath] = read_file_history.get(fpath, 0) + 1
                        if read_file_history[fpath] >= 3:
                            msg = f"THRASHING: File '{fpath}' read {read_file_history[fpath]} times. Since your memory is pruned, you MUST use 'record_finding' to save the important details of this file now, or you will likely lose them and repeat this action."
                            logger.warning(f"chat_service.thrashing | {msg}")
                            messages.append({"role": "system", "content": f"THRASHING WARNING: {msg}"})

                    if tname in GUI_TOOLS:
                        gui_tools_used_this_turn.add(tname)

                # Execute via the new Host Orchestrator (handles internal + external + policy)
                # We still use ToolSelector for extraction and basic classification, 
                # but execution goes through mcp_host.
                execution_tasks = []
                for call in tool_calls:
                    execution_tasks.append(mcp_host.execute(call["name"], call["parameters"]))
                
                tool_results = await asyncio.gather(*execution_tasks)
                
                # Check for confirmations or errors
                stop_turn = False
                any_error = False
                for res in tool_results:
                    if res and res.get("status") == "requires_confirmation":
                        yield {"type": "tool_result", "data": res}
                        stop_turn = True
                    elif res and res.get("status") == "error":
                        any_error = True
                        # We still report errors but might continue if others succeeded
                        pass

                if stop_turn:
                    # Termination: AI turn ends here. 
                    # Frontend will display 'CONFIRM' button. 
                    # Once confirmed, frontend sends a NEW message to resume.
                    logger.info("chat_service.process", extra={"status": "paused", "reason": "tool_requires_confirmation"})
                    return 
                
                if any_error:
                    consecutive_error_count += 1
                else:
                    consecutive_error_count = 0

                if consecutive_error_count >= 3:
                     yield "\n\n⚠️ **System Notice**: Three consecutive tool errors detected. Stopping for safety."
                     break

                # Flag to track if any finding was recorded in this batch of tool results
                finding_recorded_this_batch = False

                for r in tool_results:
                    conversation_manager.add_tool_result(session_id, r)
                    
                    # Real-time Discovery Notification
                    if r and r.get("is_finding"):
                        # Update turn counter when a finding is successfully recorded
                        turns_since_last_finding = 0
                        finding_enforcement_active = False # Reset enforcement
                        section = r.get("section", "Finding")
                        content = r.get("content", "")
                        yield {"type": "discovery", "section": section, "content": content}
                        # Important: After a finding, we usually want to stop and let the user see it
                        # unless it was a very small update. Let's force a break to be safe.
                        yield {"type": "discovery_checkpoint", "message": "Summary recorded. Waiting for your review."}
                        finding_recorded_this_batch = True
                        break # HAND OVER TO USER after a finding is recorded
                    
                    yield {"type": "tool_result", "data": r}
                
                # Increment finding pressure if no finding was in this batch
                if not any(res.get("is_finding") for res in tool_results if res):
                    turns_since_last_finding += 1
                 # Check if any GUI tool has been called too many times without verification
                overused_gui_tools = [
                    name for name in gui_tools_used_this_turn
                    if tool_call_counts.get(name, 0) >= 3
                ]
                
                verification_hint = ""
                if overused_gui_tools:
                    names_str = ", ".join(f"'{t}'" for t in overused_gui_tools)
                    verification_hint = (
                        f"\n\n🔁 **Loop Warning**: Tool(s) {names_str} have been called {tool_call_counts.get(overused_gui_tools[0], 0)}+ times. "
                        "If you are repeating a GUI action because you cannot confirm the result, STOP and use "
                        "'get_clipboard_text' to read the current value from the clipboard (after pressing Ctrl+C in the app). "
                        "Do NOT repeat the same GUI action again without first verifying what is on screen via clipboard."
                    )
                    logger.warning(f"chat_service.gui_loop_guard | tools={overused_gui_tools} counts={tool_call_counts}")

                error_context = ""
                if any_error:
                    error_context = "\n\n⚠️ **ATTENTION**: Some tools returned errors. Please analyze the 'error' fields below and adjust your next steps to fix these issues before proceeding."

                follow_up = (
                    f"Tool execution results:\n```json\n"
                    + json.dumps(tool_results, indent=2)
                    + "\n```\n\n"
                    "Step Complete. VERIFY the results. If a tool failed, FIX it in the next turn. "
                    "If you used a GUI tool, verify the result using 'get_clipboard_text' (Ctrl+C first) before continuing. "
                    "Otherwise, continue with the PLAN until the objective is reached."
                    + error_context
                    + verification_hint
                )
                messages.append({"role": "user", "content": follow_up})
                conversation_manager.append(session_id, "user", follow_up)
                yield {"type": "tool_followup_start"}

                if current_turn >= max_turns:
                    limit_msg = f"\n\n⚠️ **System Notice**: Reached maximum turn limit ({max_turns}). Please let me know if you would like me to continue or if you have any questions about the work done so far."
                    yield limit_msg
                    conversation_manager.append(session_id, "assistant", limit_msg)
                    break

        except Exception as e:
            logger.exception("chat_service.loop_error")
            yield f"\n\n⚠️ **System Error**: {str(e)}"
        
        yield {"type": "granular_status", "label": "Task Finished", "detail": "All steps completed."}

    async def analyze_code(
        self, code: str, language: str = "python", task: str = "analyze"
    ) -> AsyncGenerator[Any, None]:
        prompt = prompt_builder.build_task_prompt(task, language=language, code=code)
        messages = [
            {"role": "system", "content": await prompt_builder.build_system_prompt(query=code)},
            {"role": "user", "content": prompt},
        ]
        async for chunk in self._run_reasoning_loop(messages):
            yield chunk

    async def generate_code(
        self, user_prompt: str, language: str = "python", context: Optional[str] = None
    ) -> AsyncGenerator[Any, None]:
        prompt = prompt_builder.build_task_prompt("generate", language=language, prompt=user_prompt)
        if context:
            prompt += f"\n\nExisting code context:\n```{language}\n{context}\n```"
        messages = [
            {"role": "system", "content": await prompt_builder.build_system_prompt()},
            {"role": "user", "content": prompt},
        ]
        async for chunk in self._run_reasoning_loop(messages):
            yield chunk

    async def debug_code(
        self, code: str, error: str, language: str = "python"
    ) -> AsyncGenerator[Any, None]:
        from services.code_debugger import code_debugger
        debug_prompt = code_debugger.build_debug_prompt(code, error, language)
        messages = [
            {"role": "system", "content": await prompt_builder.build_system_prompt()},
            {"role": "user", "content": debug_prompt},
        ]
        async for chunk in self._run_reasoning_loop(messages):
            yield chunk

    def get_session_stats(self) -> dict:
        return conversation_manager.stats()


# Singleton instance
chat_service = ChatService()
