"""Demo 2: Multi-step task planning with Judge→Select→Execute→Verify."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.core import BioHermesAgent


async def main():
    agent = BioHermesAgent(log_dir="demo_output/demo2/logs")
    print("=" * 60)
    print("Demo 2: Multi-Step Task Planning (Core Demo)")
    print("Architecture: Judge → Select → Execute → Verify")
    print("=" * 60)

    task = "解析目录下所有PDF财务报表，提取资产负债表中的关键指标，生成对比报告"
    print(f"\nTask: {task}\n")

    session = await agent.run(task)

    print("\n── Judge Phase ──")
    if session.judge_result:
        jr = session.judge_result
        print(f"  Task Type: {jr.task_type}")
        print(f"  Complexity: {jr.complexity}")
        print(f"  Recommended Tools: {jr.recommended_tools}")
        print(f"  Strategy: {jr.execution_strategy}")
        print(f"  Risk Factors: {jr.risk_factors}")

    print("\n── Plan (Select Phase) ──")
    for step in session.steps:
        print(f"  {step.index}. [{step.tool_name or 'builtin'}] {step.description}")

    print("\n── Execution ──")
    for step in session.steps:
        icon = {"completed": "OK", "completed_fallback": "FALLBACK", "skipped": "SKIP"}.get(step.status, step.status.upper())
        duration = f"{step.duration()}s" if step.duration() else ""
        tools = ", ".join(f"{tc.name}({tc.duration()}s)" for tc in step.tool_calls)
        print(f"  Step {step.index}: [{icon}] {step.description} {duration}" + (f" → {tools}" if tools else ""))

    print("\n── Verify Phase ──")
    if session.verify_result:
        vr = session.verify_result
        print(f"  Passed: {vr.passed}")
        for check in vr.checks:
            mark = "OK" if check["passed"] else "FAIL"
            print(f"  [{mark}] {check['name']}: {check['detail']}")
        for w in vr.warnings:
            print(f"  [WARN] {w}")
        for e in vr.errors:
            print(f"  [ERR] {e}")

    print(f"\nResult: {session.result}")
    print(f"Duration: {session.duration()}s")


if __name__ == "__main__":
    asyncio.run(main())
