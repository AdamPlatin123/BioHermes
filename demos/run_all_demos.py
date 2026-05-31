"""Run 10 diverse demo scenarios and collect execution logs."""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from biohermes.agent.core import BioHermesAgent

# 10 demo scenarios covering all competition evaluation dimensions
DEMOS = [
    {
        "id": "demo_01_simple_parse",
        "title": "简单 PDF 解析",
        "task": "解析 /home/zhidao-2/outputs/bayesian_forest_carbon.pdf",
        "desc": "单个学术论文PDF解析，验证基础文档理解能力",
    },
    {
        "id": "demo_02_extract_structure",
        "title": "结构化信息提取",
        "task": "解析 /home/zhidao-2/outputs/bayesian_hierarchical_forest_carbon.pdf，提取所有章节标题、公式和元数据",
        "desc": "学术论文结构化抽取，包含多级标题和 LaTeX 公式",
    },
    {
        "id": "demo_03_table_extract",
        "title": "表格提取与验证",
        "task": "解析 /home/zhidao-2/cds_ddi_alert_system/ai_ddi_alert_cds.pdf，提取所有表格并验证数字一致性",
        "desc": "医药文献表格提取，含跨页表格和数字验证",
    },
    {
        "id": "demo_04_english_task",
        "title": "英文任务指令",
        "task": "Parse this PDF /home/zhidao-2/outputs/bayesian_forest_carbon.pdf and extract all tables with structural analysis",
        "desc": "英文自然语言指令，验证多语言任务理解",
    },
    {
        "id": "demo_05_complex_pipeline",
        "title": "复杂多步 Pipeline",
        "task": "对 /home/zhidao-2/outputs/bayesian_hierarchical_forest_carbon.pdf 执行完整处理：解析文档、提取结构化信息、提取表格、清洗数据、生成报告",
        "desc": "5步完整 pipeline 执行，验证多步规划能力",
    },
    {
        "id": "demo_06_batch_hint",
        "title": "批量处理提示",
        "task": "批量解析以下文件：/home/zhidao-2/outputs/bayesian_forest_carbon.pdf 和 /home/zhidao-2/cds_ddi_alert_system/ai_ddi_alert_cds.pdf",
        "desc": "多文件批量处理，验证并发策略选择",
    },
    {
        "id": "demo_07_financial_report",
        "title": "财务报告分析",
        "task": "解析 /home/zhidao-2/cds_ddi_alert_system/ai_ddi_alert_cds.pdf 的财务相关表格，验证数字合计与明细的一致性",
        "desc": "模拟财务报表解析，验证 Level 3 一致性检查",
    },
    {
        "id": "demo_08_deep_analysis",
        "title": "深度文档分析",
        "task": "对 /home/zhidao-2/outputs/bayesian_forest_carbon.pdf 进行深度解析，提取章节结构、所有表格数据、LaTeX公式，并验证提取完整性",
        "desc": "综合文档理解，验证 Verify 三级校验闭环",
    },
    {
        "id": "demo_09_error_recovery",
        "title": "异常恢复演示",
        "task": "解析不存在的文件 /nonexistent/file.pdf，然后降级解析 /home/zhidao-2/outputs/bayesian_forest_carbon.pdf",
        "desc": "验证三级恢复机制：文件不存在时的错误处理与降级",
    },
    {
        "id": "demo_10_knowledge_pipeline",
        "title": "知识库 Pipeline",
        "task": "构建知识库索引：解析 /home/zhidao-2/cds_ddi_alert_system/ai_ddi_alert_cds.pdf，提取结构化数据和表格，生成摘要报告",
        "desc": "端到端知识库构建，验证完整 Agent 闭环",
    },
]


async def run_demo(agent, demo, output_dir):
    """Run a single demo and save the log."""
    print(f"\n{'='*60}")
    print(f"  {demo['id']}: {demo['title']}")
    print(f"  {demo['desc']}")
    print(f"  Task: {demo['task'][:80]}")
    print(f"{'='*60}")

    start = time.time()
    session = await agent.run(demo['task'])
    elapsed = time.time() - start

    result = session.to_dict()

    status_icon = "OK" if result['status'] == 'completed' else "FAIL"
    print(f"\n  [{status_icon}] Status: {result['status']} | Duration: {result['duration']}s | Steps: {len(result['steps'])}")

    if result['judge_result']:
        jr = result['judge_result']
        print(f"  Judge: type={jr['task_type']}, complexity={jr['complexity']}, strategy={jr['execution_strategy']}")

    for step in result['steps']:
        icon = {"completed": "OK", "completed_fallback": "FB", "skipped": "SKIP"}.get(step['status'], step['status'])
        print(f"    Step {step['index']}: [{icon}] {step['description']} ({step['duration']}s)")

    if result['verify_result']:
        vr = result['verify_result']
        print(f"  Verify: {'PASSED' if vr['passed'] else 'FAILED'} ({len(vr['checks'])} checks)")

    # Save log
    log_file = os.path.join(output_dir, f"{demo['id']}.json")
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump({
            "demo_id": demo['id'],
            "demo_title": demo['title'],
            "demo_description": demo['desc'],
            "session": result,
        }, f, ensure_ascii=False, indent=2)

    print(f"  Log saved: {log_file}")
    return demo['id'], result['status'] == 'completed', result['duration']


async def main():
    output_dir = "demo_output/logs"
    os.makedirs(output_dir, exist_ok=True)

    agent = BioHermesAgent(log_dir=output_dir)

    results = []
    for demo in DEMOS:
        demo_id, success, duration = await run_demo(agent, demo, output_dir)
        results.append({"id": demo_id, "title": demo['title'], "success": success, "duration": duration})

    print(f"\n\n{'='*60}")
    print("DEMO RUN SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for r in results if r['success'])
    total_time = sum(r['duration'] for r in results)

    for r in results:
        icon = "OK" if r['success'] else "FAIL"
        print(f"  [{icon}] {r['id']}: {r['title']} ({r['duration']}s)")

    print(f"\n  Total: {passed}/{len(results)} passed | {total_time:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
