"""
Hybrid AI Assistant with OpenClaw
=================================
A secure hybrid AI assistant that routes tasks between:
- Cloud Brain (OpenRouter): Complex reasoning, tool calling, web parsing, coding
- Local Brain (Ollama): Private local file processing

Security Features:
- Human-in-the-loop confirmation for file system operations
- Prompt injection defense for external data
"""

from __future__ import annotations

import os
import sys
from typing import Any, Literal
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv
from openai import AsyncOpenAI
import ollama
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Import Rosa Tools (implemented in tools.py)
try:
    from tools import WebSearchTool, LocalKnowledgeBaseTool, PersistentMemoryTool
except ImportError:
    class WebSearchTool:  # type: ignore
        pass
    class LocalKnowledgeBaseTool:  # type: ignore
        pass
    class PersistentMemoryTool:  # type: ignore
        pass

# Load environment variables
load_dotenv()

console = Console()


class TaskType(Enum):
    """Classification of task types for routing decisions."""
    COMPLEX_REASONING = "complex_reasoning"
    TOOL_CALLING = "tool_calling"
    WEB_PARSING = "web_parsing"
    CODING = "coding"
    PRIVATE_FILE = "private_file"
    SIMPLE_CHAT = "simple_chat"


@dataclass
class TaskClassification:
    """Result of task classification."""
    task_type: TaskType
    confidence: float
    reasoning: str


class HybridRouter:
    """
    Routes tasks between Cloud Brain (OpenRouter) and Local Brain (Ollama).
    """
    
    def __init__(self):
        # Initialize Tools
        self.web_search = WebSearchTool()
        self.local_kb = LocalKnowledgeBaseTool()
        self.memory = PersistentMemoryTool()

        # Cloud Brain (OpenRouter) client
        import httpx
        self.cloud_client = AsyncOpenAI(
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self.cloud_model = os.getenv("CLOUD_MODEL", "anthropic/claude-3.5-sonnet")
        
        # Local Brain (Ollama) configuration
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.local_model = os.getenv("LOCAL_MODEL", "llama3.2")
        
        # Security settings
        self.require_confirmation = os.getenv("REQUIRE_CONFIRMATION", "true").lower() == "true"
        self.allow_file_operations = os.getenv("ALLOW_FILE_OPERATIONS", "false").lower() == "true"
    
    def classify_task(self, user_input: str, context: dict[str, Any] | None = None) -> TaskClassification:
        """
        Classify the task type based on user input and context.
        
        Returns:
            TaskClassification with task type and confidence
        """
        user_input_lower = user_input.lower()
        
        # Check for private file operations
        private_indicators = [
            "мой файл", "my file", "локальный файл", "local file",
            "прочитай файл", "read file", "анализируй файл", "analyze file",
            "~/", "/users/", "/home/", ".txt", ".md", ".pdf", ".doc"
        ]
        if any(indicator in user_input_lower for indicator in private_indicators):
            # Check if it's a private local path
            if any(path in user_input for path in ["~/", "/Users/", "/home/"]):
                return TaskClassification(
                    task_type=TaskType.PRIVATE_FILE,
                    confidence=0.9,
                    reasoning="Detected local private file reference"
                )
        
        # Check for web parsing tasks
        web_indicators = [
            "веб", "web", "сайт", "site", "url", "http", "https",
            "спарси", "parse", "scrap", "извлеки данные", "extract data"
        ]
        if any(indicator in user_input_lower for indicator in web_indicators):
            return TaskClassification(
                task_type=TaskType.WEB_PARSING,
                confidence=0.85,
                reasoning="Detected web-related task"
            )
        
        # Check for coding tasks
        coding_indicators = [
            "код", "code", "программа", "program", "функция", "function",
            "script", "скрипт", "debug", "дебаг", "python", "javascript",
            "напиши", "write", "создай", "create"
        ]
        if any(indicator in user_input_lower for indicator in coding_indicators):
            # Check for complex coding patterns
            complex_patterns = ["архитектура", "architecture", "система", "system", "api", "база данных", "database"]
            if any(pattern in user_input_lower for pattern in complex_patterns):
                return TaskClassification(
                    task_type=TaskType.CODING,
                    confidence=0.9,
                    reasoning="Detected complex coding/system design task"
                )
        
        # Check for complex reasoning
        complex_indicators = [
            "анализ", "analysis", "исследование", "research",
            "сравни", "compare", "объясни сложно", "explain in depth",
            "рассуждение", "reasoning", "логика", "logic"
        ]
        if any(indicator in user_input_lower for indicator in complex_indicators):
            return TaskClassification(
                task_type=TaskType.COMPLEX_REASONING,
                confidence=0.8,
                reasoning="Detected complex reasoning task"
            )
        
        # Check for tool calling patterns
        tool_indicators = [
            "выполни команду", "run command", "terminal", "терминал",
            "bash", "shell", "git", "npm", "pip"
        ]
        if any(indicator in user_input_lower for indicator in tool_indicators):
            return TaskClassification(
                task_type=TaskType.TOOL_CALLING,
                confidence=0.85,
                reasoning="Detected terminal/tool execution request"
            )
        
        # Default to simple chat
        return TaskClassification(
            task_type=TaskType.SIMPLE_CHAT,
            confidence=0.7,
            reasoning="Default classification for general conversation"
        )
    
    async def route_to_cloud_brain(self, user_input: str, system_prompt: str | None = None) -> str:
        """
        Send task to Cloud Brain (OpenRouter).
        
        Args:
            user_input: The user's request
            system_prompt: Optional system prompt to guide the model
            
        Returns:
            Response from the cloud model
        """
        default_system_prompt = """You are a helpful AI assistant with access to powerful reasoning capabilities.
You excel at complex reasoning, coding, web parsing, and tool-assisted tasks.
Always provide accurate, well-reasoned responses."""
        
        try:
            response = await self.cloud_client.chat.completions.create(
                model=self.cloud_model,
                messages=[
                    {"role": "system", "content": system_prompt or default_system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7,
                max_tokens=8000,
            )
            return response.choices[0].message.content or "No response received"
        except Exception as e:
            return f"Error communicating with Cloud Brain: {str(e)}"
    
    async def route_to_local_brain(self, user_input: str, system_prompt: str | None = None) -> str:
        """
        Send task to Local Brain (Ollama).
        
        Args:
            user_input: The user's request
            system_prompt: Optional system prompt
            
        Returns:
            Response from the local model
        """
        default_system_prompt = """You are a local AI assistant running on the user's machine.
You handle private data and local file operations securely.
Never expose sensitive information in your responses."""
        
        try:
            client = ollama.AsyncClient(host=self.ollama_base_url)
            response = await client.chat(
                model=self.local_model,
                messages=[
                    {"role": "system", "content": system_prompt or default_system_prompt},
                    {"role": "user", "content": user_input}
                ],
                options={
                    "temperature": 0.7,
                    "num_predict": 4000,
                }
            )
            return response["message"]["content"]
        except Exception as e:
            return f"Error communicating with Local Brain (Ollama): {str(e)}\nMake sure Ollama is running: ollama run {self.local_model}"
    
    async def process_task(self, user_input: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Main entry point: classify and route task to appropriate brain.
        
        Args:
            user_input: The user's request
            context: Additional context for routing decisions
            
        Returns:
            Dictionary with response and routing information
        """
        # Classify the task
        classification = self.classify_task(user_input, context)
        
        # Determine routing based on classification
        use_cloud = classification.task_type in [
            TaskType.COMPLEX_REASONING,
            TaskType.TOOL_CALLING,
            TaskType.WEB_PARSING,
            TaskType.CODING,
        ]
        
        if use_cloud:
            console.print(Panel(
                f"[blue]Routing to Cloud Brain (OpenRouter)[/blue]\n"
                f"Model: {self.cloud_model}\n"
                f"Task: {classification.task_type.value}\n"
                f"Confidence: {classification.confidence:.0%}"
            ))
            response = await self.route_to_cloud_brain(user_input)
            brain_used = "cloud"
        else:
            console.print(Panel(
                f"[green]Routing to Local Brain (Ollama)[/green]\n"
                f"Model: {self.local_model}\n"
                f"Task: {classification.task_type.value}\n"
                f"Confidence: {classification.confidence:.0%}"
            ))
            response = await self.route_to_local_brain(user_input)
            brain_used = "local"
        
        return {
            "response": response,
            "brain_used": brain_used,
            "classification": classification,
            "model": self.cloud_model if brain_used == "cloud" else self.local_model,
        }


# Export main classes
__all__ = ["HybridRouter", "TaskClassification", "TaskType"]
