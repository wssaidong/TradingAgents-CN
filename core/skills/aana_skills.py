"""
AAna Skill 桥接层

把 AAna-CN-Integration 仓库的 4 个实盘验证 Skill 注册到 TA-CN Skill 体系：

    from core.skills.aana_skills import screen, monitor, run_backtest, get_stats

通过 AANA_SKILLS + SkillConverter 可进一步转为 OpenAI Function Calling 工具定义。
上游仓库缺失时 import 不报错，仅在真正调用时抛 RuntimeError（错误隔离设计）。
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from typing import Any, Callable, List

from .models import (
    PythonImplementation,
    SkillMetadata,
    SkillParameter,
    SkillReturns,
)

AANA_INTEGRATION_DIR = os.environ.get(
    "AANA_INTEGRATION_DIR",
    os.path.expanduser("~/code/AAna-CN-Integration"),
)

_EXPORT_TABLE = {
    "screen": ("aana-afternoon-screen", "screen"),
    "monitor": ("aana-intraday-monitor", "monitor"),
    "run_backtest": ("aana-backtest", "run_backtest"),
    "get_stats": ("aana-recommendation-tracker", "get_stats"),
}


def _load_function(skill_dir: str, function_name: str) -> Callable[..., Any]:
    # skill 目录名是 kebab-case（Agent Skills 规范），不能直接作为 Python 模块名导入，
    # 与 AAna-CN-Integration 的 run_skill.py 一致：优先 underscore 模块名，失败按文件路径加载
    module_name = f"skills.{skill_dir.replace('-', '_')}"
    impl_path = os.path.join(AANA_INTEGRATION_DIR, "skills", skill_dir, "impl.py")
    try:
        if AANA_INTEGRATION_DIR not in sys.path:
            sys.path.insert(0, AANA_INTEGRATION_DIR)
        module = importlib.import_module(module_name)
    except ImportError:
        if not os.path.exists(impl_path):
            raise RuntimeError(
                f"无法加载 AAna Skill {skill_dir}，"
                f"请确认 {impl_path} 存在且可访问（可用 AANA_INTEGRATION_DIR 环境变量覆盖路径）"
            )
        spec = importlib.util.spec_from_file_location(f"_aana_{skill_dir.replace('-', '_')}", impl_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return getattr(module, function_name)


def __getattr__(name: str) -> Callable[..., Any]:
    if name in _EXPORT_TABLE:
        skill_dir, function_name = _EXPORT_TABLE[name]
        return _load_function(skill_dir, function_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(list(globals().keys()) + list(_EXPORT_TABLE.keys()))


AANA_SKILLS: List[SkillMetadata] = [
    SkillMetadata(
        name="aana-afternoon-screen",
        description="AAna 尾盘综合打分 Top N：综合 PE/PB/ROE/涨幅/量比/主力净流入/RSI 7 因子打分，输出候选股及评分明细（90 天回测验证）。",
        category="screening",
        when_to_use="用户需要尾盘（14:45）选股、次日候选股推荐或综合打分排名时使用。",
        parameters=[
            SkillParameter(name="codes", type="array", description="候选股票代码列表（6 位数字），不传则全市场筛选", required=False),
            SkillParameter(name="top", type="integer", description="返回 Top N", required=False, default=5),
            SkillParameter(name="weights", type="object", description="评分权重 JSON（预留，上游暂未生效）", required=False),
            SkillParameter(name="sentiment_score", type="integer", description="大盘情绪分 (0-100)，默认 50 中性", required=False, default=50),
            SkillParameter(name="position_ratio", type="number", description="建议仓位比例 (0-1)", required=False, default=0.5),
            SkillParameter(name="record_feedback", type="boolean", description="是否写入 rec_feedback.csv（Skill 调用默认 False）", required=False, default=False),
        ],
        returns=SkillReturns(
            type="array",
            description="每项包含 code/name/score/price/change_pct/reason/risk/stop_loss/target_price/macd_gold",
        ),
        implementation=PythonImplementation(module="core.skills.aana_skills", function="screen"),
        tags=["a股", "尾盘", "选股", "打分"],
    ),
    SkillMetadata(
        name="aana-intraday-monitor",
        description="AAna 盘中异动监控：实时监控默认股票池的涨跌幅异动与告警。",
        category="monitoring",
        when_to_use="用户需要盘中实时异动监控、涨跌幅告警时使用（盘中时段才有非空结果）。",
        parameters=[
            SkillParameter(name="codes", type="array", description="指定监控的股票代码列表，不传用默认池", required=False),
            SkillParameter(name="alert_threshold_pct", type="number", description="涨跌幅告警阈值（%），默认 7", required=False, default=7.0),
        ],
        returns=SkillReturns(
            type="array",
            description="每项包含 code/name/alert_type/change_pct/msg",
        ),
        implementation=PythonImplementation(module="core.skills.aana_skills", function="monitor"),
        tags=["a股", "盘中", "监控"],
    ),
    SkillMetadata(
        name="aana-backtest",
        description="AAna 回测：按持有天数/止损等参数回测选股策略，返回收益、胜率、夏普等指标。",
        category="backtest",
        when_to_use="用户需要验证选股策略的历史表现（收益率/胜率/夏普/最大回撤）时使用。",
        parameters=[
            SkillParameter(name="codes", type="array", description="股票代码列表，不传走全量", required=False),
            SkillParameter(name="hold_days", type="integer", description="持有天数", required=False, default=5),
            SkillParameter(name="stop_loss_pct", type="number", description="止损比例 (0-1)，0 表示不止损", required=False, default=0.0),
            SkillParameter(name="start_date", type="string", description="起始日期 YYYY-MM-DD 或 YYYYMMDD", required=False),
            SkillParameter(name="end_date", type="string", description="结束日期", required=False),
        ],
        returns=SkillReturns(
            type="object",
            description="total_return_pct / trades / win_rate / sharpe_ratio / max_drawdown_pct / avg_hold_days",
        ),
        implementation=PythonImplementation(module="core.skills.aana_skills", function="run_backtest"),
        tags=["回测", "量化"],
    ),
    SkillMetadata(
        name="aana-recommendation-tracker",
        description="AAna 推荐追踪胜率统计：按股票/时间窗统计历史推荐命中率与胜率。",
        category="screening",
        when_to_use="用户需要查询历史推荐胜率、验证某只股票过往推荐表现时使用。",
        parameters=[
            SkillParameter(name="codes", type="array", description="股票代码列表（过滤），单只传 [code]", required=False),
            SkillParameter(name="start_date", type="string", description="起始日期 YYYY-MM-DD", required=False),
            SkillParameter(name="end_date", type="string", description="结束日期（预留）", required=False),
            SkillParameter(name="horizon_days", type="integer", description="评估窗口 (1/3/5/15)", required=False, default=5),
        ],
        returns=SkillReturns(
            type="object",
            description="total_count / hit_count / win_rate / avg_return_pct / best_stock / worst_stock",
        ),
        implementation=PythonImplementation(module="core.skills.aana_skills", function="get_stats"),
        tags=["推荐追踪", "胜率"],
    ),
]
