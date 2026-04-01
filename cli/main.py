"""Auto-Tessell CLI 진입점."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


def _setup_logging(verbose: bool, json_log: bool) -> None:
    from core.utils.logging import configure_logging
    configure_logging(verbose=verbose, json=json_log)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="DEBUG 레벨 로깅")
@click.option("--json-log", is_flag=True, help="JSON 포맷 로깅 (CI/파이프라인용)")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, json_log: bool) -> None:
    """Auto-Tessell: CAD/메쉬 → OpenFOAM polyMesh 자동 생성."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["json_log"] = json_log
    _setup_logging(verbose, json_log)


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="geometry_report.json 저장 경로 (기본: <input>.geometry_report.json)")
@click.option("--dry-run", is_flag=True, help="분석만 수행, 파일 저장 없음")
@click.pass_context
def analyze(ctx: click.Context, input_file: Path, output: Path | None, dry_run: bool) -> None:
    """입력 파일을 분석하고 geometry_report.json을 생성한다."""
    from core.analyzer.geometry_analyzer import GeometryAnalyzer

    verbose = ctx.obj.get("verbose", False)
    analyzer = GeometryAnalyzer(verbose=verbose)

    console.print(f"[bold cyan]Analyzing[/bold cyan] {input_file}")
    report = analyzer.analyze(input_file)

    if dry_run:
        console.print_json(report.model_dump_json(indent=2))
        return

    out_path = output or input_file.with_suffix(".geometry_report.json")
    out_path.write_text(report.model_dump_json(indent=2))
    console.print(f"[bold green]✓[/bold green] geometry_report.json → {out_path}")

    # Rich 요약
    g = report.geometry
    s = g.surface
    console.print(
        f"[dim]  {g.bounding_box.characteristic_length:.3f}L  "
        f"{s.num_faces} faces  "
        f"watertight={'✓' if s.is_watertight else '✗'}  "
        f"manifold={'✓' if s.is_manifold else '✗'}  "
        f"flow={report.flow_estimation.type}  "
        f"issues={len(report.issues)}[/dim]"
    )


# ---------------------------------------------------------------------------
# preprocess
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--geometry-report", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--tier", default=None, help="Tier 힌트 (netgen이면 CAD 패스스루)")
@click.option("--no-repair", is_flag=True)
@click.option("--force-repair", is_flag=True)
@click.option("--surface-remesh", is_flag=True)
@click.option("--remesh-target-faces", type=int, default=None)
@click.option("--allow-ai-fallback", is_flag=True, help="L3 AI 표면 재생성 허용 (GPU 필요)")
@click.pass_context
def preprocess(
    ctx: click.Context,
    input_file: Path,
    geometry_report: Path | None,
    output: Path | None,
    tier: str | None,
    no_repair: bool,
    force_repair: bool,
    surface_remesh: bool,
    remesh_target_faces: int | None,
    allow_ai_fallback: bool,
) -> None:
    """표면 수리, 포맷 변환, 리메쉬를 수행하고 preprocessed.stl을 생성한다."""
    from core.preprocessor.pipeline import Preprocessor
    from core.schemas import GeometryReport

    console.print(f"[bold cyan]Preprocessing[/bold cyan] {input_file}")

    # geometry_report 로딩 또는 즉석 분석
    if geometry_report is not None:
        report_obj = GeometryReport.model_validate_json(geometry_report.read_text())
    else:
        from core.analyzer.geometry_analyzer import GeometryAnalyzer
        console.print("[dim]geometry_report 없음 — 즉석 분석 수행[/dim]")
        analyzer = GeometryAnalyzer(verbose=ctx.obj.get("verbose", False))
        report_obj = analyzer.analyze(input_file)

    out_dir = output or input_file.parent / (input_file.stem + "_preprocessed")
    preprocessor = Preprocessor()

    try:
        out_stl, prep_report = preprocessor.run(
            input_path=input_file,
            geometry_report=report_obj,
            output_dir=out_dir,
            tier_hint=tier,
            no_repair=no_repair,
            surface_remesh=surface_remesh,
            remesh_target_faces=remesh_target_faces,
            allow_ai_fallback=allow_ai_fallback,
        )
        # preprocessed_report.json 저장
        report_json_path = out_dir / "preprocessed_report.json"
        report_json_path.write_text(prep_report.model_dump_json(indent=2))

        console.print(f"[bold green]✓[/bold green] preprocessed.stl → {out_stl}")
        console.print(f"[bold green]✓[/bold green] preprocessed_report.json → {report_json_path}")

        summary = prep_report.preprocessing_summary
        fv = summary.final_validation
        console.print(
            f"[dim]faces={fv.num_faces}  "
            f"watertight={fv.is_watertight}  "
            f"manifold={fv.is_manifold}  "
            f"time={summary.total_time_seconds:.2f}s[/dim]"
        )
    except Exception as exc:
        console.print(f"[bold red]ERROR[/bold red] {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# strategize
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--geometry-report", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--preprocessed-report", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--quality-report", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--tier", default="auto")
@click.option("--quality", default="standard",
              type=click.Choice(["draft", "standard", "fine"], case_sensitive=False),
              help="품질 레벨 (draft=빠른검증 / standard=엔지니어링 / fine=최종CFD)")
@click.option("--iteration", type=int, default=1)
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.pass_context
def strategize(
    ctx: click.Context,
    geometry_report: Path,
    preprocessed_report: Path | None,
    quality_report: Path | None,
    tier: str,
    quality: str,
    iteration: int,
    output: Path | None,
) -> None:
    """메쉬 생성 전략(mesh_strategy.json)을 수립한다."""
    from core.schemas import GeometryReport, PreprocessedReport, QualityLevel, QualityReport
    from core.strategist.strategy_planner import StrategyPlanner

    console.print("[bold cyan]Strategizing[/bold cyan]")

    geo = GeometryReport.model_validate_json(geometry_report.read_text())

    pre: PreprocessedReport | None = None
    if preprocessed_report is not None:
        pre = PreprocessedReport.model_validate_json(preprocessed_report.read_text())

    qual: QualityReport | None = None
    if quality_report is not None:
        qual = QualityReport.model_validate_json(quality_report.read_text())

    planner = StrategyPlanner()
    strategy = planner.plan(
        geometry_report=geo,
        preprocessed_report=pre,
        quality_report=qual,
        tier_hint=tier,
        iteration=iteration,
        quality_level=QualityLevel(quality),
    )

    out_path = output or Path("mesh_strategy.json")
    out_path.write_text(strategy.model_dump_json(indent=2))
    console.print(f"[bold green]Strategy written[/bold green] -> {out_path}")
    console.print_json(strategy.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--strategy", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--preprocessed", type=click.Path(path_type=Path), default=None,
              help="전처리된 STL/CAD 파일 경로 (기본: strategy의 surface_mesh.input_file)")
@click.option("--tier", default=None,
              help="Tier 강제 지정 (strategy.selected_tier 무시). "
                   "선택: core, netgen, snappy, cfmesh, tetwild")
@click.option("--quality", default=None,
              type=click.Choice(["draft", "standard", "fine"], case_sensitive=False),
              help="품질 레벨 재정의 (strategy.quality_level 무시)")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("./case"))
@click.pass_context
def generate(
    ctx: click.Context,
    strategy: Path,
    preprocessed: Path | None,
    tier: str | None,
    quality: str | None,
    output: Path,
) -> None:
    """mesh_strategy.json에 따라 메쉬를 생성하고 polyMesh를 출력한다."""
    import time

    from core.generator.pipeline import MeshGenerator
    from core.schemas import MeshStrategy, QualityLevel

    console.print(f"[bold cyan]Generating[/bold cyan] → {output}")

    # strategy 로딩
    strategy_obj = MeshStrategy.model_validate_json(strategy.read_text())

    # Tier 강제 지정 처리
    if tier is not None:
        console.print(f"[dim]Tier 강제 지정: {strategy_obj.selected_tier} → {tier}[/dim]")
        strategy_obj.selected_tier = tier
        strategy_obj.fallback_tiers = []

    # quality_level 재정의
    if quality is not None:
        console.print(f"[dim]quality_level 재정의: {strategy_obj.quality_level} → {quality}[/dim]")
        strategy_obj.quality_level = QualityLevel(quality)

    # 전처리 파일 경로 결정
    if preprocessed is not None:
        preprocessed_path = preprocessed
    else:
        preprocessed_path = Path(strategy_obj.surface_mesh.input_file)

    console.print(f"[dim]selected_tier={strategy_obj.selected_tier}  "
                  f"fallback={strategy_obj.fallback_tiers}[/dim]")
    console.print(f"[dim]preprocessed={preprocessed_path}[/dim]")

    case_dir = output
    generator = MeshGenerator()

    t0 = time.monotonic()
    try:
        log = generator.run(
            strategy=strategy_obj,
            preprocessed_path=preprocessed_path,
            case_dir=case_dir,
        )
    except Exception as exc:
        console.print(f"[bold red]ERROR[/bold red] Generator 예상치 못한 오류: {exc}")
        sys.exit(1)

    time.monotonic() - t0
    summary = log.execution_summary

    # 결과 출력
    successful = next(
        (a for a in summary.tiers_attempted if a.status == "success"), None
    )

    if successful:
        console.print(
            f"[bold green]✓[/bold green] 메쉬 생성 완료 "
            f"(tier={successful.tier}, time={successful.time_seconds:.1f}s)"
        )
        console.print(f"[bold green]✓[/bold green] polyMesh → {summary.output_dir}")
    else:
        console.print("[bold red]✗[/bold red] 모든 Tier 실패")
        for attempt in summary.tiers_attempted:
            console.print(f"  [red]✗[/red] {attempt.tier}: {attempt.error_message}")

    # generator_log.json 저장
    log_path = case_dir / "generator_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log.model_dump_json(indent=2))
    console.print(f"[dim]generator_log.json → {log_path}[/dim]")

    if not successful:
        sys.exit(1)


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--case", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--geometry-report", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--generator-log", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--strategy", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--iteration", type=int, default=1, show_default=True)
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="quality_report.json 저장 경로 (기본: <case>/quality_report.json)")
@click.pass_context
def evaluate(
    ctx: click.Context,
    case: Path,
    geometry_report: Path,
    generator_log: Path | None,
    strategy: Path | None,
    iteration: int,
    output: Path | None,
) -> None:
    """생성된 메쉬 품질을 검증하고 quality_report.json을 생성한다."""
    import time

    from core.evaluator.metrics import AdditionalMetricsComputer
    from core.evaluator.quality_checker import MeshQualityChecker
    from core.evaluator.report import EvaluationReporter, render_terminal
    from core.schemas import GeometryFidelity, MeshStrategy

    console.print(f"[bold cyan]Evaluating[/bold cyan] {case}")

    # strategy 로딩
    strategy_obj: MeshStrategy | None = None
    if strategy is not None:
        strategy_obj = MeshStrategy.model_validate_json(strategy.read_text())
    tier_name = strategy_obj.selected_tier if strategy_obj else "unknown"

    # checkMesh 실행
    checker = MeshQualityChecker()
    t0 = time.monotonic()
    try:
        checkmesh_result = checker.run(case)
    except FileNotFoundError as exc:
        console.print(
            f"[bold red]ERROR[/bold red] OpenFOAM 미설치 또는 checkMesh를 찾을 수 없습니다: {exc}"
        )
        sys.exit(1)

    elapsed = time.monotonic() - t0

    # 추가 지표 계산
    metrics_computer = AdditionalMetricsComputer()
    metrics = metrics_computer.compute(case)

    # geometry fidelity (현재는 선택사항 — geometry_report 기반 계산은 미구현)
    geo_fidelity: GeometryFidelity | None = None

    # 판정 및 리포트 생성
    reporter = EvaluationReporter()
    report = reporter.evaluate(
        checkmesh=checkmesh_result,
        strategy=strategy_obj,
        metrics=metrics,
        geometry_fidelity=geo_fidelity,
        iteration=iteration,
        tier=tier_name,
        elapsed=elapsed,
    )

    # 터미널 출력
    render_terminal(report)

    # JSON 저장
    out_path = output or (case / "quality_report.json")
    out_path.write_text(report.model_dump_json(indent=2))
    console.print(f"\n[bold green]✓[/bold green] quality_report.json → {out_path}")

    # FAIL 시 비-0 종료코드
    if report.evaluation_summary.verdict.value == "FAIL":
        sys.exit(2)


# ---------------------------------------------------------------------------
# run (전체 파이프라인)
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("./case"))
@click.option("--tier", default="auto", show_default=True,
              type=click.Choice(["auto", "core", "netgen", "snappy", "cfmesh", "tetwild"]))
@click.option("--quality", default="standard", show_default=True,
              type=click.Choice(["draft", "standard", "fine"], case_sensitive=False),
              help="품질 레벨 (draft=빠른검증 / standard=엔지니어링 / fine=최종CFD)")
@click.option("--element-size", type=float, default=None)
@click.option("--max-iterations", type=int, default=3, show_default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--allow-ai-fallback", is_flag=True, help="L3 AI 표면 재생성 허용 (GPU 필요)")
@click.pass_context
def run(
    ctx: click.Context,
    input_file: Path,
    output: Path,
    tier: str,
    quality: str,
    element_size: float | None,
    max_iterations: int,
    dry_run: bool,
    allow_ai_fallback: bool,
) -> None:
    """전체 파이프라인(Analyze→Preprocess→Strategize→Generate→Evaluate)을 실행한다."""
    from core.pipeline.orchestrator import PipelineOrchestrator

    ctx.obj.get("verbose", False) if ctx.obj else False
    console.print(f"[bold magenta]Auto-Tessell[/bold magenta] {input_file} → {output}")
    console.print(f"  quality={quality}  tier={tier}  max_iter={max_iterations}")

    orchestrator = PipelineOrchestrator()
    result = orchestrator.run(
        input_path=input_file,
        output_dir=output,
        quality_level=quality,
        tier_hint=tier,
        max_iterations=max_iterations,
        dry_run=dry_run,
        element_size=element_size,
        allow_ai_fallback=allow_ai_fallback,
    )

    if dry_run:
        console.print("[bold cyan]Dry-run 완료[/bold cyan] — 전략 수립까지만 실행")
        if result.strategy:
            s = result.strategy
            console.print(f"  Tier: {s.selected_tier}  Fallback: {s.fallback_tiers}")
            console.print(f"  Quality: {s.quality_level}  Flow: {s.flow_type}")
            console.print(f"  Cell size: {s.surface_mesh.target_cell_size}")
        return

    # Rich 리포트 출력
    if result.quality_report:
        from core.evaluator.report import render_terminal
        render_terminal(result.quality_report)

    if result.boundary_patches:
        console.print("\n[bold]Boundary patches:[/bold]")
        for p in result.boundary_patches:
            console.print(f"  {p['name']:20s} → {p['type']:15s} ({p['nFaces']} faces)")

    if result.success:
        console.print(f"[bold green]✓ PASS[/bold green] ({result.iterations} iteration, {result.total_time_seconds:.1f}s)")
    else:
        console.print(f"[bold red]✗ FAIL[/bold red] — {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
