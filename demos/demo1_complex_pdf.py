"""Demo 1: Complex PDF academic paper parsing."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.core import BioHermesAgent


async def main():
    agent = BioHermesAgent(log_dir="demo_output/demo1/logs")
    print("=" * 60)
    print("Demo 1: Complex PDF Academic Paper Parsing")
    print("=" * 60)

    task = "解析一份双栏排版的学术论文PDF，提取标题、摘要、章节、表格和LaTeX公式"
    print(f"\nTask: {task}\n")

    session = await agent.run(task)
    print(f"\nStatus: {session.status.value}")
    print(f"Judge: type={session.judge_result.task_type}, complexity={session.judge_result.complexity}")
    print(f"Plan: {len(session.steps)} steps")
    for step in session.steps:
        icon = "OK" if step.status == "completed" else step.status.upper()
        tools = ", ".join(tc.name for tc in step.tool_calls)
        print(f"  Step {step.index}: [{icon}] {step.description}" + (f" ({tools})" if tools else ""))
    print(f"\nResult: {session.result}")
    print(f"Duration: {session.duration()}s")

    if session.verify_result:
        print(f"Verify: {'PASSED' if session.verify_result.passed else 'FAILED'}")
        for w in session.verify_result.warnings:
            print(f"  Warning: {w}")


if __name__ == "__main__":
    asyncio.run(main())
