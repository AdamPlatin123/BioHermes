"""Demo 4: Complex table and chart parsing."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.core import BioHermesAgent


async def main():
    agent = BioHermesAgent(log_dir="demo_output/demo4/logs")
    print("=" * 60)
    print("Demo 4: Complex Table & Chart Parsing")
    print("=" * 60)

    task = "解析含跨页表格、合并单元格和密集数字的工程报告，验证数字一致性"
    print(f"\nTask: {task}\n")

    session = await agent.run(task)

    print(f"\nStatus: {session.status.value}")
    if session.judge_result:
        print(f"Features: {session.judge_result.document_features}")

    print("\nSteps:")
    for step in session.steps:
        icon = "OK" if step.status == "completed" else step.status.upper()
        print(f"  Step {step.index}: [{icon}] {step.description}")

    if session.verify_result:
        print(f"\nConsistency checks:")
        for check in session.verify_result.checks:
            if "total" in check["name"].lower() or "consist" in check["name"].lower():
                mark = "OK" if check["passed"] else "FAIL"
                print(f"  [{mark}] {check['name']}: {check['detail']}")

    print(f"\nResult: {session.result}")


if __name__ == "__main__":
    asyncio.run(main())
