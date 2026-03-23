"""Tests for HybridRouter task classification."""

import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from hybrid_assistant import HybridRouter, TaskType


@pytest.fixture
def router():
    return HybridRouter()


def test_classify_private_file(router):
    c = router.classify_task("прочитай файл ~/Documents/secret.txt")
    assert c.task_type == TaskType.PRIVATE_FILE
    assert c.confidence >= 0.8


def test_classify_web(router):
    c = router.classify_task("parse https://example.com")
    assert c.task_type == TaskType.WEB_PARSING


def test_classify_coding(router):
    # Router requires both coding keywords AND complex pattern (architecture/system/api/database)
    c = router.classify_task("write a python script for a database api system")
    assert c.task_type == TaskType.CODING


def test_classify_complex_reasoning(router):
    c = router.classify_task("analysis of recent market trends")
    assert c.task_type == TaskType.COMPLEX_REASONING


def test_classify_tool_calling(router):
    c = router.classify_task("run command: git status")
    assert c.task_type == TaskType.TOOL_CALLING


def test_classify_simple_chat(router):
    c = router.classify_task("hello, how are you?")
    assert c.task_type == TaskType.SIMPLE_CHAT


def test_cloud_routing(router):
    c = router.classify_task("write a FastAPI backend with database")
    assert c.task_type in (TaskType.CODING, TaskType.COMPLEX_REASONING, TaskType.WEB_PARSING, TaskType.TOOL_CALLING)
