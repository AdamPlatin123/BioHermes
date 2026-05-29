"""Demo 5: End-to-end knowledge pipeline."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.core import BioHermesAgent


async def main():
    agent = BioHermesAgent(log_dir="demo_output/demo5/logs")
    print("=" * 60)
    print("Demo 5: End-to-End Knowledge Pipeline")
    print("=" * 60)

    task = "从原始文档到结构化知识的完整pipeline：摄入→MinerU解析→智能切片→结构化索引→验证报告"
    print(f"\nTask: {task}\n")

    session = await agent.run(task)

    print(f"\nStatus: {session.status.value}")
    if session.judge_result:
        print(f"Judge: type={session.judge_result.task_type}, strategy={session.judge_result.execution_strategy}")

    print("\nPipeline Phases:")
    for step in session.steps:
        icon = "OK" if step.status == "completed" else step.status.upper()
        print(f"  Phase {step.index}: [{icon}] {step.description}")

    if session.verify_result:
        print(f"\nVerify: {'PASSED' if session.verify_result.passed else 'FAILED'}")
        print(f"  Checks: {len(session.verify_result.checks)}")
        print(f"  Warnings: {len(session.verify_result.warnings)}")

    print(f"\nResult: {session.result}")
    print(f"Duration: {session.duration()}s")


if __name__ == "__main__":
    asyncio.run(main())
