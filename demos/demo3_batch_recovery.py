"""Demo 3: Batch processing with error recovery."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.core import BioHermesAgent


async def main():
    agent = BioHermesAgent(log_dir="demo_output/demo3/logs")
    print("=" * 60)
    print("Demo 3: Batch Processing with Error Recovery")
    print("=" * 60)

    task = "批量处理50份混合格式文档（含故意损坏文件），自动恢复失败项"
    print(f"\nTask: {task}\n")

    session = await agent.run(task)

    print(f"\nStatus: {session.status.value}")
    print(f"Judge: type={session.judge_result.task_type}, strategy={session.judge_result.execution_strategy}")

    completed = sum(1 for s in session.steps if s.status in ("completed", "completed_fallback"))
    skipped = sum(1 for s in session.steps if s.status == "skipped")
    failed = sum(1 for s in session.steps if s.status == "failed")

    print(f"\nSteps: {completed} completed, {skipped} skipped, {failed} failed / {len(session.steps)} total")
    print(f"Retry count: {session.retry_count}")

    for step in session.steps:
        if step.status != "completed":
            print(f"  Step {step.index}: [{step.status}] {step.description}")
            if step.error:
                print(f"    Error: {step.error}")

    print(f"\nResult: {session.result}")


if __name__ == "__main__":
    asyncio.run(main())
