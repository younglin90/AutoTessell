"""Auto-Tessell CLI 진입점."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from core.max_cells_policy import resolve_max_bg_cells_cap
from core.utils.openfoam_utils import get_openfoam_label_size

console = Console()


def _print_dep_summary() -> None:
    """설치/미설치 라이브러리 요약을 출력한다.

    설치된 것: 개수만 표시.
    미설치(선택): 노랑으로 나열.
    미설치(필수): 빨강으로 나열 + 경고.
    상세 정보는 `auto-tessell doctor` 참조.
    """
    from core.runtime.dependency_status import collect_dependency_statuses

    statuses = collect_dependency_statuses()
    ok: list[str] = []
    missing_optional: list[str] = []
    missing_required: list[str] = []

    for s in statuses:
        if s.detected:
            ok.append(s.name)
        elif s.optional:
            missing_optional.append(s.name)
        else:
            missing_required.append(s.name)

    # 설치된 것: 개수만
    ok_str = f"[green]✓ {len(ok)}개 설치됨[/green]"

    # 미설치 선택
    opt_str = (
        "  [yellow]✗ " + "  ✗ ".join(missing_optional) + "[/yellow]"
        if missing_optional else ""
    )

    # 미설치 필수
    req_str = (
        "  [bold red]✗ " + "  ✗ ".join(missing_required) + " (필수!)[/bold red]"
        if missing_required else ""
    )

    console.print(f"[dim]deps:[/dim] {ok_str}{opt_str}{req_str}")

    if missing_optional or missing_required:
        console.print(
            f"[dim]  미설치 {len(missing_optional) + len(missing_required)}개"
            f" — `auto-tessell doctor` 로 상세 확인 및 설치 방법 안내[/dim]"
        )


def _setup_logging(verbose: bool, json_log: bool) -> None:
    from core.utils.logging import configure_logging
    configure_logging(verbose=verbose, json=json_log)


def _resolve_effective_max_cells(max_cells: int, quality: str) -> tuple[int, int]:
    """OpenFOAM label 크기와 quality에 따라 max_cells 상한을 적용한다."""
    label_bits = get_openfoam_label_size()
    cap = resolve_max_bg_cells_cap(str(quality).lower(), label_bits)
    return min(max_cells, cap), label_bits


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
# doctor
# ---------------------------------------------------------------------------


@cli.command()
def doctor() -> None:
    """런타임 의존성 탐지 결과(설치/미설치/선택)를 표로 출력한다."""
    from rich.table import Table

    from core.runtime.dependency_status import collect_dependency_statuses

    rows = collect_dependency_statuses()
    table = Table(title="Runtime Dependency Status")
    table.add_column("Dependency", style="cyan")
    table.add_column("Category")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Fallback")
    table.add_column("Action")

    for row in rows:
        status = "[green]installed[/green]" if row.detected else "[red]missing[/red]"
        dtype = "optional" if row.optional else "required"
        table.add_row(row.name, row.category, dtype, status, row.fallback, row.action)

    console.print(table)


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

    # geometry fidelity 계산
    geo_fidelity: GeometryFidelity | None = None
    try:
        from core.evaluator.fidelity import GeometryFidelityChecker
        from core.schemas import GeometryReport

        geo_report = GeometryReport.model_validate_json(geometry_report.read_text())
        if geo_report.file_path:
            checker = GeometryFidelityChecker()
            # diagonal은 strategy에서 또는 geometry_report에서 추출
            diagonal = geo_report.geometry.bounding_box.diagonal if geo_report.geometry else 1.0
            geo_fidelity = checker.compute(
                original_file=Path(geo_report.file_path),
                case_dir=case,
                diagonal=diagonal,
            )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]⚠ geometry fidelity 계산 실패: {exc}[/yellow]")

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
# --- Tier / Quality ---
@click.option("--tier", default="auto", show_default=True,
              type=click.Choice([
                  "auto", "core", "netgen", "snappy", "cfmesh", "tetwild",
                  "wildmesh", "mmg3d", "algohex", "robust_hex",
                  "jigsaw", "jigsaw_fallback",
                  "meshpy", "hex_classy", "classy_blocks",
                  "gmsh_hex", "cinolib_hex", "voro_poly",
                  "polyhedral", "hohqmesh", "2d",
                  "native_tet", "native_hex", "native_poly",
              ]),
              help="볼륨 메쉬 엔진 (auto=품질레벨에 따라 자동)")
@click.option("--quality", default="standard", show_default=True,
              type=click.Choice(["draft", "standard", "fine"], case_sensitive=False),
              help="품질 레벨 (draft=빠른검증 / standard=엔지니어링 / fine=최종CFD)")
# --- Library selection ---
@click.option("--repair-engine", default="auto", show_default=True,
              type=click.Choice(["auto", "pymeshfix", "trimesh", "none"]),
              help="L1 표면 수리 라이브러리")
@click.option("--remesh-engine", default="auto", show_default=True,
              type=click.Choice(["auto", "quadwild", "vorpalite", "pyacvd", "pymeshlab", "none"]),
              help="L2 표면 리메쉬 라이브러리 (vorpalite=geogram, 최고 품질)")
@click.option("--volume-engine", default="auto", show_default=True,
              type=click.Choice([
                  "auto", "tetwild", "netgen", "snappy", "cfmesh",
                  "wildmesh", "mmg3d", "algohex", "robust_hex",
                  "jigsaw", "jigsaw_fallback",
                  "meshpy", "hex_classy", "classy_blocks",
                  "gmsh_hex", "cinolib_hex", "voro_poly",
                  "polyhedral", "hohqmesh", "2d",
                  "native_tet", "native_hex", "native_poly",
              ]),
              help="볼륨 메쉬 엔진 (--tier와 동일, 더 명시적 이름)")
@click.option("--checker-engine", default="auto", show_default=True,
              type=click.Choice(["auto", "openfoam", "native"]),
              help="품질 검증 엔진. v0.4 이후 auto=NativeMeshChecker 기본 "
                   "(openfoam 명시 시에만 OpenFOAM checkMesh 사용, 교차 검증용).")
@click.option("--cad-engine", default="auto", show_default=True,
              type=click.Choice(["auto", "cadquery", "gmsh"]),
              help="CAD 파일(STEP/IGES) 변환 라이브러리")
@click.option("--postprocess-engine", default="auto", show_default=True,
              type=click.Choice(["auto", "mmg", "none"]),
              help="볼륨 메쉬 후처리 (mmg=MMG3D 품질 개선)")
# --- Cell size control ---
@click.option("--element-size", type=float, default=None, help="표면 셀 크기 override [m]")
@click.option("--base-cell-size", type=float, default=None, help="배경 셀 크기 override [m]")
@click.option("--min-cell-size", type=float, default=None, help="최소 셀 크기 override [m]")
@click.option("--base-cell-num", type=int, default=None, help="특성길이 대비 분할 수 (기본: 50, 작을수록 거친 메쉬)")
# --- Domain control ---
@click.option("--domain-upstream", type=float, default=None, help="업스트림 배수 (기본: draft=3, std=5, fine=10)")
@click.option("--domain-downstream", type=float, default=None, help="다운스트림 배수 (기본: draft=5, std=10, fine=20)")
@click.option("--domain-lateral", type=float, default=None, help="측면 배수 (기본: draft=2, std=3, fine=5)")
@click.option("--domain-scale", type=float, default=1.0, help="도메인 전체 스케일 팩터")
# --- Max cell limit ---
@click.option("--max-cells", type=click.IntRange(min=1), default=None, help="최대 셀 수 제한 (초과 시 셀 크기 자동 확대)")
# --- Boundary Layer ---
@click.option("--bl-layers", type=int, default=None, help="BL 레이어 수 (0=비활성)")
@click.option("--bl-first-height", type=float, default=None, help="첫 번째 BL 높이 [m]. --target-yplus 와 함께 쓰면 자동 계산값 override.")
@click.option(
    "--fluid",
    type=click.Choice([
        "air", "water", "oil", "custom",
        # beta2274: 추가 fluid presets (BLConfig.flow_fluid_preset 동등).
        "air_sea_level", "air_20C", "air_0C",
        "water_20C", "water_4C",
        "oil_SAE10W30", "glycol_50pct",
    ]),
    default="air", show_default=True,
    help="유체 종류 — y⁺ 자동 계산 시 동점성 계수 조회 기준.",
)
@click.option(
    "--target-yplus", type=float, default=None,
    help=(
        "목표 y⁺ 값 (예: 1.0 = low-Re, 30 = 벽함수). "
        "지정 시 --flow-velocity + geometry bbox 로 첫 BL 층 두께를 자동 계산. "
        "--bl-first-height 미지정 시에만 유효."
    ),
)
@click.option(
    "--kinematic-viscosity", type=float, default=None,
    help="직접 동점성 계수 지정 [m²/s]. --fluid 무시됨.",
)
@click.option("--bl-growth-ratio", type=float, default=None, help="BL 성장비 (기본: 1.2)")
# --- Preprocessor ---
@click.option("--no-repair", is_flag=True, help="표면 수리 건너뛰기")
@click.option("--force-remesh", is_flag=True, help="L2 리메쉬 강제 실행")
@click.option("--remesh-target-faces", type=int, default=None, help="리메쉬 목표 삼각형 수")
@click.option("--allow-ai-fallback", is_flag=True, help="L3 AI 표면 재생성 허용 (GPU 필요)")
@click.option("--strict-tier", is_flag=True, help="명시 tier(auto 아님)에서 fallback tier 비활성화")
# --- TetWild specific ---
@click.option("--tetwild-epsilon", type=float, default=None, help="TetWild epsilon (draft=0.02, std=0.001)")
@click.option("--tetwild-stop-energy", type=float, default=None, help="TetWild stop energy (draft=20, std=10)")
# --- snappyHexMesh specific ---
@click.option("--snappy-castellated-level", type=str, default=None, help="castellated refinement [min,max] (예: 2,3)")
@click.option("--snappy-snap-tolerance", type=float, default=None, help="snap tolerance (기본: 2.0)")
@click.option("--snappy-snap-iterations", type=int, default=None, help="snap solve iterations (기본: 5)")
# --- Generic tier params (v0.4.0-beta20+) ---
@click.option(
    "--tier-param", "tier_param", multiple=True,
    metavar="KEY=VALUE",
    help=(
        "generic tier 파라미터 override (반복 가능, 예: --tier-param seed_density=20 "
        "--tier-param max_iter=4). native_tet/hex/poly HARNESS_PARAMS 테이블과 동일한 "
        "키를 받는다. int/float/bool/str 은 자동 추론."
    ),
)
# --- Output control ---
@click.option(
    "--mesh-type",
    type=click.Choice(["auto", "tet", "hex_dominant", "poly"]),
    default="auto",
    show_default=True,
    help="메쉬 타입 (v0.4 신규): tet / hex_dominant / poly. auto=Strategist 가 quality/geometry 기반 자동 선택",
)
@click.option(
    "--prefer-native/--legacy-repair", "prefer_native", default=True,
    show_default=True,
    help="v0.4.0-beta26+ 기본 True. Preprocessor L1 을 자체 native_repair 로 수행. "
         "--legacy-repair 명시 시에만 pymeshfix/trimesh 경로로 강제 전환 (opt-out).",
)
@click.option(
    "--prefer-native-tier", is_flag=True,
    help="v0.4.0-beta23+ native-first tier: Strategist 가 native_tet/hex/poly 를 "
         "primary 로 선택 (기존 tier 는 fallback). mesh_type 명시 필요.",
)
@click.option(
    "--cross-engine-fallback", is_flag=True,
    help="v0.4.0-beta68+ poly mesh_type 이 완전 실패하면 hex_dominant 로 1회 "
         "자동 재시도. 실패 시 결과 error 필드에 [cross_engine_fallback poly→hex] 프리픽스.",
)
@click.option(
    "--enable-vvv9h-apply", is_flag=True,
    help="beta2319 fix + beta2344 — Klingner 2008 §3.5 edge-contract real apply 활성. "
         "환경변수 AUTO_TESSELL_VVV9H_APPLY=1 동등. sliver 격감용 (실험적).",
)
@click.option(
    "--enable-offplane-steiner", is_flag=True,
    help="beta2318 + beta2344 — Klingner-Shewchuk 2008 §4.1 off-plane Steiner "
         "exudation real apply 활성. 환경변수 AUTO_TESSELL_OFFPLANE_STEINER=1 동등.",
)
@click.option(
    "--enable-vvv9j-apply", is_flag=True,
    help="beta2346 — VVV9J SLIM global-pass real apply (smoothing 강화). "
         "환경변수 AUTO_TESSELL_VVV9J_APPLY=1 동등.",
)
@click.option(
    "--enable-vvv9k-apply", is_flag=True,
    help="beta2346 — VVV9K priority-queue main-loop real apply. "
         "환경변수 AUTO_TESSELL_VVV9K_APPLY=1 동등 (monotone guard, beta2320).",
)
@click.option(
    "--enable-vvv9p-apply", is_flag=True,
    help="beta2346 — VVV9P multi-face removal real apply. "
         "환경변수 AUTO_TESSELL_VVV9P_APPLY=1 동등 (monotone guard, beta2321).",
)
@click.option(
    "--parallel-delaunay", is_flag=True,
    help="beta2365-2366 — V > 30000 시 ProcessPoolExecutor 기반 chunked "
         "Delaunay 병렬화. 환경변수 AUTO_TESSELL_PARALLEL_DELAUNAY=1 동등.",
)
@click.option(
    "--seed-gwn", is_flag=True,
    help="beta2392 — 시드 inside test 에 Jacobson 2013 generalized "
         "winding number 사용 (SI/non-manifold 입력 robust). beta2394 의 "
         "auto-fallback (SI 검출 시 자동 ON) 보다 강제. "
         "환경변수 AUTO_TESSELL_SEED_GWN=1 동등.",
)
@click.option(
    "--stellar-split", is_flag=True,
    help="beta2374-2378 — Stellar 4-op queue 의 split-pass 활성. "
         "fine quality 는 자동 ON; 명시 force-on. "
         "환경변수 AUTO_TESSELL_STELLAR_SPLIT=1 동등.",
)
@click.option(
    "--poly-budget-s", type=float, default=None,
    help="beta2381 — poly Voronoi escalate 의 wall-clock budget (초). "
         "기본 90s. 환경변수 AUTO_TESSELL_POLY_BUDGET_S 동등.",
)
@click.option(
    "--bl-floor-ratio", type=float, default=None,
    help="beta2447 — BL curvature_adaptive_thickness floor ratio "
         "(base_thickness 의 fraction, 0.0-1.0). 1.0=uniform, 0.5=cfMesh, "
         "0.3=aggressive adaptive. 기본 1.0. "
         "환경변수 AUTO_TESSELL_BL_FLOOR_RATIO 동등.",
)
@click.option(
    "--hex-snap-budget-s", type=float, default=None,
    help="beta2457 — hex feature snap pass 의 wall-clock budget (초). "
         "0=off (기본). 설정 시 강제 cap (hard hex 메쉬에서 hang 방지). "
         "환경변수 AUTO_TESSELL_HEX_WWW7_BUDGET_S 동등.",
)
@click.option(
    "--lloyd-plateau-thresh", type=float, default=None,
    help="beta2454/beta2458 — poly Lloyd CVT plateau early-exit threshold "
         "(rel-disp/bbox). 기본 1e-4. 작을수록 더 수렴 (느림), 클수록 일찍 종료. "
         "환경변수 AUTO_TESSELL_LLOYD_PLATEAU_THRESH 동등.",
)
@click.option(
    "--patch-cap", type=int, default=None,
    help="beta2459 — polyMesh patch count 상한 (이상은 wall_misc 로 병합). "
         "기본 64. 늘리면 patch 별 BC 세분화 가능하나 boundary 파일 증가. "
         "환경변수 AUTO_TESSELL_PATCH_CAP 동등.",
)
@click.option(
    "--flow-velocity", type=float, default=1.0, show_default=True,
    help="v0.4.0-beta78+ 유입 속도 [m/s]. 0/U 자동 생성 기준값. "
         "turbulence 필드 (k, epsilon/omega) 에 반영.",
)
@click.option(
    "--turbulence-model",
    type=click.Choice(["kEpsilon", "kOmegaSST"]),
    default="kEpsilon", show_default=True,
    help="난류 모델 선택.",
)
@click.option(
    "--auto-retry",
    type=click.Choice(["off", "once", "continue"]),
    default="off",
    show_default=True,
    help="Evaluator FAIL 시 자동 재시도 모드. off(기본, 사용자가 결정) / once / continue(예전 max_iterations 루프 복원)",
)
@click.option(
    "--max-iterations",
    type=int,
    default=3,
    show_default=True,
    help="최대 재시도 횟수 (auto_retry=continue 일 때만 사용됨; deprecated, 하위호환용)",
)
@click.option("--dry-run", is_flag=True, help="전략 수립까지만 (메쉬 생성 안 함)")
@click.option("--profile", is_flag=True, help="성능 프로파일링 (단계별 소요 시간)")
@click.option("--export-vtk", "do_export_vtk", is_flag=True, help="완료 후 VTK (.vtu) 내보내기")
@click.option("--polyhedral", is_flag=True, help="Tet→Polyhedral 듀얼 변환 (polyDualMesh)")
@click.option("--parallel", type=int, default=None, help="MPI 병렬 프로세서 수 (decomposeParDict 생성)")
@click.option("--verbose-mesh", is_flag=True, help="메쉬 생성 상세 로그")
@click.pass_context
def run(
    ctx: click.Context,
    input_file: Path,
    output: Path,
    tier: str,
    quality: str,
    repair_engine: str,
    remesh_engine: str,
    volume_engine: str,
    checker_engine: str,
    cad_engine: str,
    postprocess_engine: str,
    element_size: float | None,
    base_cell_size: float | None,
    min_cell_size: float | None,
    base_cell_num: int | None,
    domain_upstream: float | None,
    domain_downstream: float | None,
    domain_lateral: float | None,
    domain_scale: float,
    max_cells: int | None,
    bl_layers: int | None,
    bl_first_height: float | None,
    fluid: str,
    target_yplus: float | None,
    kinematic_viscosity: float | None,
    bl_growth_ratio: float | None,
    no_repair: bool,
    force_remesh: bool,
    remesh_target_faces: int | None,
    allow_ai_fallback: bool,
    strict_tier: bool,
    tetwild_epsilon: float | None,
    tetwild_stop_energy: float | None,
    snappy_castellated_level: str | None,
    snappy_snap_tolerance: float | None,
    snappy_snap_iterations: int | None,
    tier_param: tuple[str, ...],
    mesh_type: str,
    prefer_native: bool,
    prefer_native_tier: bool,
    cross_engine_fallback: bool,
    enable_vvv9h_apply: bool,
    enable_offplane_steiner: bool,
    enable_vvv9j_apply: bool,
    enable_vvv9k_apply: bool,
    enable_vvv9p_apply: bool,
    parallel_delaunay: bool,
    seed_gwn: bool,
    stellar_split: bool,
    poly_budget_s: float | None,
    bl_floor_ratio: float | None,
    hex_snap_budget_s: float | None,
    lloyd_plateau_thresh: float | None,
    patch_cap: int | None,
    flow_velocity: float,
    turbulence_model: str,
    auto_retry: str,
    max_iterations: int,
    dry_run: bool,
    profile: bool,
    do_export_vtk: bool,
    polyhedral: bool,
    parallel: int | None,
    verbose_mesh: bool,
) -> None:
    """전체 파이프라인(Analyze→Preprocess→Strategize→Generate→Evaluate)을 실행한다."""
    from core.pipeline.orchestrator import PipelineOrchestrator

    # volume_engine이 지정되면 tier를 override
    effective_tier = tier
    if volume_engine != "auto":
        # beta2349 — 이전엔 4 entries 만 — native_tet/hex/poly + 나머지 ~12 choices
        # 가 fall back 으로 tier (auto) 가 되어 GUI/CLI 사용자의 명시 선택 무시.
        # 모든 click.Choice 값을 tier_hint 와 동일하게 매핑 (identity).
        tier_map = {
            "tetwild": "tetwild", "netgen": "netgen",
            "snappy": "snappy", "cfmesh": "cfmesh",
            "wildmesh": "wildmesh", "mmg3d": "mmg3d",
            "algohex": "algohex", "robust_hex": "robust_hex",
            "jigsaw": "jigsaw", "jigsaw_fallback": "jigsaw_fallback",
            "meshpy": "meshpy", "hex_classy": "hex_classy",
            "classy_blocks": "classy_blocks",
            "gmsh_hex": "gmsh_hex", "cinolib_hex": "cinolib_hex",
            "voro_poly": "voro_poly", "polyhedral": "polyhedral",
            "hohqmesh": "hohqmesh", "2d": "2d",
            "native_tet": "native_tet", "native_hex": "native_hex",
            "native_poly": "native_poly",
        }
        effective_tier = tier_map.get(volume_engine, tier)

    # repair_engine=none이면 no_repair 강제
    if repair_engine == "none":
        no_repair = True

    # beta2344 + beta2346 — 실험적 V-series real-apply 플래그를 환경변수로 변환.
    # 사용자가 GUI/CLI 에서 toggle 한 결과를 mesher 가 inspect 할 수 있게.
    import os as _os_v9
    if enable_vvv9h_apply:
        _os_v9.environ["AUTO_TESSELL_VVV9H_APPLY"] = "1"
    if enable_offplane_steiner:
        _os_v9.environ["AUTO_TESSELL_OFFPLANE_STEINER"] = "1"
    if enable_vvv9j_apply:
        _os_v9.environ["AUTO_TESSELL_VVV9J_APPLY"] = "1"
    if enable_vvv9k_apply:
        _os_v9.environ["AUTO_TESSELL_VVV9K_APPLY"] = "1"
    if enable_vvv9p_apply:
        _os_v9.environ["AUTO_TESSELL_VVV9P_APPLY"] = "1"
    if parallel_delaunay:
        _os_v9.environ["AUTO_TESSELL_PARALLEL_DELAUNAY"] = "1"
    # C-CLI-1 / beta2418 — 추가 env wiring (GUI/CLI parity).
    if seed_gwn:
        _os_v9.environ["AUTO_TESSELL_SEED_GWN"] = "1"
    if stellar_split:
        _os_v9.environ["AUTO_TESSELL_STELLAR_SPLIT"] = "1"
    if poly_budget_s is not None:
        _os_v9.environ["AUTO_TESSELL_POLY_BUDGET_S"] = str(float(poly_budget_s))
    # C-CLI-2 / beta2448 — BL floor ratio CLI exposure.
    if bl_floor_ratio is not None:
        _os_v9.environ["AUTO_TESSELL_BL_FLOOR_RATIO"] = str(float(bl_floor_ratio))
    # C-CLI-3 / beta2457 — hex feature snap budget CLI exposure.
    if hex_snap_budget_s is not None:
        _os_v9.environ["AUTO_TESSELL_HEX_WWW7_BUDGET_S"] = str(float(hex_snap_budget_s))
    # C-CLI-4 / beta2458 — Lloyd plateau threshold CLI exposure.
    if lloyd_plateau_thresh is not None:
        _os_v9.environ["AUTO_TESSELL_LLOYD_PLATEAU_THRESH"] = str(float(lloyd_plateau_thresh))
    # C-CLI-5 / beta2459 — polyMesh patch count cap CLI exposure.
    if patch_cap is not None:
        _os_v9.environ["AUTO_TESSELL_PATCH_CAP"] = str(int(patch_cap))

    console.print(f"[bold magenta]Auto-Tessell[/bold magenta] {input_file} → {output}")
    console.print(
        f"  quality={quality}  mesh_type={mesh_type}  tier={effective_tier}  "
        f"auto_retry={auto_retry}  max_iter={max_iterations}  "
        f"prefer_native={prefer_native}"
    )
    _print_dep_summary()
    if any(e != "auto" for e in [repair_engine, remesh_engine, volume_engine, checker_engine, cad_engine, postprocess_engine]):
        engines = []
        if repair_engine != "auto":
            engines.append(f"repair={repair_engine}")
        if remesh_engine != "auto":
            engines.append(f"remesh={remesh_engine}")
        if volume_engine != "auto":
            engines.append(f"volume={volume_engine}")
        if checker_engine != "auto":
            engines.append(f"checker={checker_engine}")
        if cad_engine != "auto":
            engines.append(f"cad={cad_engine}")
        if postprocess_engine != "auto":
            engines.append(f"postprocess={postprocess_engine}")
        console.print(f"  engines: {', '.join(engines)}")

    # CLI 옵션을 tier_specific_params로 모음
    tier_params: dict[str, object] = {}
    tier_params["repair_engine"] = repair_engine
    tier_params["remesh_engine"] = remesh_engine
    tier_params["checker_engine"] = checker_engine
    tier_params["cad_engine"] = cad_engine
    tier_params["postprocess_engine"] = postprocess_engine
    if tetwild_epsilon is not None:
        tier_params["tetwild_epsilon"] = tetwild_epsilon
    if tetwild_stop_energy is not None:
        tier_params["tetwild_stop_energy"] = tetwild_stop_energy
    if snappy_snap_tolerance is not None:
        tier_params["snappy_snap_tolerance"] = snappy_snap_tolerance
    if snappy_snap_iterations is not None:
        tier_params["snappy_snap_iterations"] = snappy_snap_iterations
    if snappy_castellated_level is not None:
        parts = snappy_castellated_level.split(",")
        if len(parts) == 2:
            tier_params["snappy_castellated_level"] = [int(parts[0]), int(parts[1])]

    # v0.4.0-beta20: generic --tier-param key=value (반복) 파싱.
    # int → float → bool → str 순서로 자동 추론.
    for _entry in tier_param or ():
        if "=" not in _entry:
            console.print(f"[yellow]⚠ --tier-param 잘못된 형식 (KEY=VALUE 필요): {_entry!r}[/yellow]")
            continue
        _k, _v = _entry.split("=", 1)
        _k = _k.strip()
        _v = _v.strip()
        if not _k:
            console.print(f"[yellow]⚠ --tier-param 빈 키: {_entry!r}[/yellow]")
            continue
        # 자동 type 추론
        _parsed: object
        if _v.lower() in {"true", "yes", "on"}:
            _parsed = True
        elif _v.lower() in {"false", "no", "off"}:
            _parsed = False
        else:
            try:
                _parsed = int(_v)
            except ValueError:
                try:
                    _parsed = float(_v)
                except ValueError:
                    _parsed = _v
        tier_params[_k] = _parsed

    effective_max_cells: int | None = None
    if max_cells is not None:
        effective_max_cells, label_bits = _resolve_effective_max_cells(max_cells, quality)
        if effective_max_cells < max_cells:
            label_name = "Int64" if label_bits >= 64 else "Int32"
            console.print(
                f"[yellow]⚠ max_cells clamp: requested={max_cells:,}, capped={effective_max_cells:,}, "
                f"label={label_name}[/yellow]"
            )

    # CLI override 옵션들을 orchestrator 전에 처리
    # element_size가 없으면 base_cell_size 또는 base_cell_num에서 유도
    effective_element_size = element_size
    if effective_element_size is None and base_cell_size is not None:
        # element_size = base_cell_size / 4 (orchestrator 내부 로직)
        effective_element_size = base_cell_size / 4

    # base_cell_num은 geometry_report 필요하므로 Analyzer 먼저 실행
    effective_base_cell_size = base_cell_size
    if effective_element_size is None and base_cell_num is not None:
        # Analyzer 실행하여 characteristic_length 획득
        from core.analyzer.geometry_analyzer import GeometryAnalyzer
        analyzer = GeometryAnalyzer()
        try:
            geometry_report = analyzer.analyze(input_file)
            if geometry_report and geometry_report.geometry.bounding_box:
                L = geometry_report.geometry.bounding_box.characteristic_length
                effective_base_cell_size = L / base_cell_num
                effective_element_size = effective_base_cell_size / 4
                console.print(f"[cyan]base_cell_num={base_cell_num} → base_cell_size={effective_base_cell_size:.6f}[/cyan]")
        except Exception as exc:
            console.print(f"[yellow]⚠ base_cell_num 계산 실패 (무시): {exc}[/yellow]")

    # BL, domain 파라미터들을 tier_specific_params에 추가 (orchestrator 내부 처리용)
    if bl_layers is not None:
        tier_params["bl_layers"] = bl_layers
    # beta96: y⁺ 자동 계산 — bl_first_height 미지정 시 target_yplus 로 역산.
    if bl_first_height is None and target_yplus is not None:
        try:
            from core.utils.yplus import estimate_first_layer_thickness  # noqa: PLC0415
            _ug = getattr(ctx, "geometry_report", None)
            _diag = None
            if _ug is not None:
                try:
                    _diag = float(_ug.geometry.bounding_box.diagonal)
                except Exception:
                    pass
            if _diag is None or _diag <= 0:
                # geometry 아직 분석 전 → input STL에서 bbox 추정
                try:
                    import trimesh as _tm  # noqa: PLC0415
                    _m = _tm.load_mesh(str(input_file))
                    _ext = _m.extents
                    _diag = float(
                        (_ext[0]**2 + _ext[1]**2 + _ext[2]**2) ** 0.5
                    )
                except Exception:
                    _diag = 1.0  # fallback: 1m
            yr = estimate_first_layer_thickness(
                flow_velocity=flow_velocity,
                characteristic_length=_diag,
                fluid=fluid,
                kinematic_viscosity=kinematic_viscosity,
                y_plus_target=target_yplus,
            )
            bl_first_height = yr.y_first
            console.print(
                f"[cyan]y⁺ 자동 계산:[/cyan] {yr.message}"
            )
        except Exception as exc:
            console.print(f"[yellow]y⁺ 계산 실패 (수동 --bl-first-height 사용): {exc}[/yellow]")
    if bl_first_height is not None:
        tier_params["bl_first_height"] = bl_first_height
    if bl_growth_ratio is not None:
        tier_params["bl_growth_ratio"] = bl_growth_ratio
    if min_cell_size is not None:
        tier_params["min_cell_size"] = min_cell_size
    # base_cell_num을 base_cell_size로 변환했으므로 전달하지 않음
    # (element_size로 이미 효과가 반영됨)

    orchestrator = PipelineOrchestrator()
    result = orchestrator.run(
        input_path=input_file,
        output_dir=output,
        quality_level=quality,
        mesh_type=mesh_type,
        tier_hint=effective_tier,
        max_iterations=max_iterations,
        auto_retry=auto_retry,
        dry_run=dry_run,
        element_size=effective_element_size,
        max_cells=effective_max_cells,
        tier_specific_params=tier_params,
        no_repair=no_repair,
        surface_remesh=force_remesh,
        remesh_engine=remesh_engine,
        allow_ai_fallback=allow_ai_fallback,
        strict_tier=strict_tier,
        validator_engine=checker_engine,
        prefer_native=prefer_native,
        prefer_native_tier=prefer_native_tier,
        cross_engine_fallback=cross_engine_fallback,
        flow_velocity=flow_velocity,
        turbulence_model=turbulence_model,
    )

    # base_cell_num은 이미 element_size로 변환되어 orchestrator에 전달됨
    # (post-processing 불필요)

    # 병렬 분해
    if parallel is not None and result.success:
        from core.utils.parallel import write_decompose_par_dict
        write_decompose_par_dict(output, n_procs=parallel)
        console.print(f"[green]✓[/green] decomposeParDict → {parallel} procs")

    if dry_run:
        console.print("[bold cyan]Dry-run 완료[/bold cyan] — 전략 수립까지만 실행")
        if result.strategy:
            s = result.strategy
            console.print(f"  Tier: {s.selected_tier}  Fallback: {s.fallback_tiers}")
            sel = s.tier_specific_params.get("engine_selection", {})
            if isinstance(sel, dict):
                src = sel.get("source", "unknown")
                reason = sel.get("reason", "unknown")
                console.print(f"  Selection: source={src} reason={reason}")
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

        # Polyhedral 변환
        if polyhedral:
            from core.generator.polyhedral import convert_to_polyhedral
            console.print("[cyan]Tet → Polyhedral 변환 중...[/cyan]")
            if convert_to_polyhedral(output):
                console.print("[green]✓[/green] Polyhedral 변환 완료 (polyDualMesh)")
            else:
                console.print("[yellow]⚠ Polyhedral 변환 실패 (OpenFOAM polyDualMesh 필요)[/yellow]")

        # VTK 내보내기
        if do_export_vtk:
            from core.utils.vtk_exporter import export_vtk
            vtk_path = export_vtk(output)
            if vtk_path:
                console.print(f"[green]✓[/green] VTK → {vtk_path}")
    else:
        console.print(f"[bold red]✗ FAIL[/bold red] — {result.error}")

        # v0.4: Evaluator FAIL + auto_retry=off 기본 경로 + tty 환경 → 사용자에게
        # 재시도 여부 prompt. 응답이 'y' 이면 orchestrator 를 auto_retry="once" 로
        # 재호출해 Strategist 의 권고 파라미터가 반영된 2 번째 시도를 수행.
        _q_report = getattr(result, "quality_report", None)
        _is_eval_fail = (
            _q_report is not None
            and getattr(getattr(_q_report, "evaluation_summary", None),
                        "verdict", None) == "FAIL"
        )
        if (
            _is_eval_fail
            and str(auto_retry).lower() == "off"
            and sys.stdin.isatty()
        ):
            try:
                ans = click.prompt(
                    "\n[?] Evaluator FAIL 입니다. Strategist 권고 파라미터로 "
                    "한 번 더 시도할까요? [y/N]",
                    default="N",
                    show_default=False,
                    type=str,
                )
            except click.exceptions.Abort:
                ans = "N"
            if str(ans).strip().lower() in ("y", "yes"):
                try:
                    _q_report.evaluation_summary.user_decision = "retry"
                except Exception:
                    pass
                console.print(
                    "[cyan]재시도 중... (auto_retry=once 로 Strategist 권고 반영)"
                    "[/cyan]"
                )
                result = orchestrator.run(
                    input_path=input_file,
                    output_dir=output,
                    quality_level=quality,
                    mesh_type=mesh_type,
                    tier_hint=effective_tier,
                    max_iterations=max_iterations,
                    auto_retry="once",
                    dry_run=dry_run,
                    element_size=effective_element_size,
                    max_cells=effective_max_cells,
                    tier_specific_params=tier_params,
                    no_repair=no_repair,
                    surface_remesh=force_remesh,
                    remesh_engine=remesh_engine,
                    allow_ai_fallback=allow_ai_fallback,
                    strict_tier=strict_tier,
                    validator_engine=checker_engine,
                    prefer_native=prefer_native,
                    prefer_native_tier=prefer_native_tier,
                    cross_engine_fallback=cross_engine_fallback,
                    flow_velocity=flow_velocity,
                    turbulence_model=turbulence_model,
                )
                if result.quality_report:
                    from core.evaluator.report import render_terminal
                    render_terminal(result.quality_report)
                if result.success:
                    console.print(
                        f"[bold green]✓ PASS (재시도 성공)[/bold green] "
                        f"({result.iterations} iteration, "
                        f"{result.total_time_seconds:.1f}s)"
                    )
                    return
                console.print(
                    f"[bold red]✗ FAIL (재시도 실패)[/bold red] — {result.error}"
                )
            else:
                try:
                    _q_report.evaluation_summary.user_decision = "accept"
                except Exception:
                    pass
                console.print(
                    "[yellow]사용자가 재시도 안 함 — 현재 mesh 유지[/yellow]"
                )
        sys.exit(1)

    # 프로파일링 출력
    if profile:
        console.print("\n[bold]Performance Profile[/bold]")
        console.print(f"  Total: {result.total_time_seconds:.2f}s")
        console.print(f"  Iterations: {result.iterations}")
        if result.generator_log:
            for t in result.generator_log.execution_summary.tiers_attempted:
                console.print(f"  {t.tier}: {t.time_seconds:.2f}s ({t.status})")


# ---------------------------------------------------------------------------
# export-vtk
# ---------------------------------------------------------------------------


@cli.command("export-vtk")
@click.argument("case_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--no-quality", is_flag=True, help="품질 필드 제외")
def export_vtk_cmd(case_dir: Path, output: Path | None, no_quality: bool) -> None:
    """생성된 메쉬를 VTK (.vtu) 포맷으로 내보낸다. ParaView에서 품질 컬러맵 시각화 가능."""
    from core.utils.vtk_exporter import export_vtk

    console.print(f"[bold cyan]Exporting VTK[/bold cyan] {case_dir}")
    result = export_vtk(case_dir, output, include_quality=not no_quality)
    if result:
        console.print(f"[bold green]✓[/bold green] VTK 파일 → {result}")
    else:
        console.print("[bold red]✗ VTK 내보내기 실패[/bold red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# export (multi-format)
# ---------------------------------------------------------------------------


@cli.command("export")
@click.argument("case_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format", "-f", "fmt",
    # beta2277: 17 formats 동기화 (mesh_exporter beta2262/2269).
    type=click.Choice([
        "su2", "fluent", "cgns",
        "vtu", "vtk", "vtp", "xdmf",
        "gmsh22", "gmsh40", "gmsh41",
        "nastran", "abaqus", "tecplot", "medit",
        "stl", "obj", "ply",
    ], case_sensitive=False),
    default=None,
    show_default=True,
    help="출력 포맷. 미지정 시 --output 확장자로 자동 감지.",
)
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="출력 파일 경로 (기본: <case_dir>/mesh.<ext>)")
def export_cmd(case_dir: Path, fmt: str | None, output: Path | None) -> None:
    """생성된 메쉬를 CFD/FEA/시각화 포맷으로 내보낸다.

    지원 포맷 (17 종, commercial-grade):
      - CFD volume: SU2, Fluent (.msh), CGNS, VTU, VTK, VTP, XDMF
      - Mesh: Gmsh 2.2/4.0/4.1, Medit, Tecplot
      - FEA: Nastran (.bdf), Abaqus (.inp)
      - Surface: STL, OBJ, PLY

    예시::

        auto-tessell export ./case -o mesh.vtu       # auto-detect VTU
        auto-tessell export ./case -f stl -o s.stl   # explicit STL
        auto-tessell export ./case -f abaqus         # default path
    """
    from core.utils.mesh_exporter import export_mesh

    fmt_label = (fmt or "auto-detect").upper()
    console.print(f"[bold cyan]Exporting mesh[/bold cyan] {case_dir} → [bold]{fmt_label}[/bold]")
    result = export_mesh(case_dir, output, fmt=fmt)  # type: ignore[arg-type]
    if result:
        console.print(f"[bold green]✓[/bold green] 파일 → {result}")
    else:
        console.print(f"[bold red]✗ 내보내기 실패[/bold red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# interactive
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("./case"))
@click.pass_context
def interactive(ctx: click.Context, input_file: Path, output: Path) -> None:
    """대화형 모드 — 각 단계를 확인하며 진행한다."""
    from core.analyzer.geometry_analyzer import GeometryAnalyzer
    from core.evaluator.metrics import AdditionalMetricsComputer
    from core.evaluator.native_checker import NativeMeshChecker
    from core.evaluator.quality_checker import MeshQualityChecker
    from core.evaluator.report import EvaluationReporter, render_terminal
    from core.generator.pipeline import MeshGenerator
    from core.preprocessor.pipeline import Preprocessor
    from core.strategist.strategy_planner import StrategyPlanner
    from core.utils.bc_writer import write_boundary_conditions
    from core.utils.boundary_classifier import classify_boundaries
    from core.utils.vtk_exporter import export_vtk

    console.print(f"[bold magenta]Auto-Tessell Interactive[/bold magenta] {input_file}")
    console.print()

    # 1. Analyze
    console.print("[bold]Step 1/6: 지오메트리 분석[/bold]")
    analyzer = GeometryAnalyzer()
    report = analyzer.analyze(input_file)
    g = report.geometry
    console.print(f"  {g.bounding_box.characteristic_length:.3f}L  {g.surface.num_faces} faces  "
                  f"watertight={'✓' if g.surface.is_watertight else '✗'}  flow={report.flow_estimation.type}")
    if not click.confirm("  계속 진행할까요?", default=True):
        return

    # 2. Preprocess
    console.print("\n[bold]Step 2/6: 표면 전처리[/bold]")
    work_dir = output / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    pp_path, pp_report = Preprocessor().run(input_file, report, work_dir)
    sq = pp_report.preprocessing_summary.surface_quality_level or "l1_repair"
    console.print(f"  surface_quality={sq}  faces={pp_report.preprocessing_summary.final_validation.num_faces}")
    if not click.confirm("  계속 진행할까요?", default=True):
        return

    # 3. Quality selection
    console.print("\n[bold]Step 3/6: 품질 레벨 선택[/bold]")
    console.print("  1) draft    — 빠른 검증 (~1초)")
    console.print("  2) standard — 엔지니어링 (~수분)")
    console.print("  3) fine     — 최종 CFD (~30분+)")
    choice = click.prompt("  선택", type=click.Choice(["1", "2", "3"]), default="1")
    quality = {"1": "draft", "2": "standard", "3": "fine"}[choice]

    # 4. Strategize
    console.print(f"\n[bold]Step 4/6: 전략 수립 (quality={quality})[/bold]")
    strategy = StrategyPlanner().plan(report, pp_report, quality_level=quality)
    console.print(f"  Tier: {strategy.selected_tier}  Cell size: {strategy.surface_mesh.target_cell_size}")
    console.print(f"  Fallback: {strategy.fallback_tiers}")
    if not click.confirm("  메쉬 생성을 시작할까요?", default=True):
        return

    # 5. Generate
    console.print(f"\n[bold]Step 5/6: 메쉬 생성 ({strategy.selected_tier})[/bold]")
    gen_log = MeshGenerator().run(strategy, pp_path, output)
    for t in gen_log.execution_summary.tiers_attempted:
        icon = "✓" if t.status == "success" else "✗"
        console.print(f"  {icon} {t.tier}: {t.status} ({t.time_seconds:.1f}s)")

    # 6. Evaluate
    console.print("\n[bold]Step 6/6: 품질 평가[/bold]")
    try:
        cm = MeshQualityChecker().run(output)
    except FileNotFoundError:
        cm = NativeMeshChecker().run(output)
    metrics = AdditionalMetricsComputer().compute(output)
    qr = EvaluationReporter().evaluate(cm, strategy, metrics, None, 1,
                                       strategy.selected_tier, 0.0, quality)
    render_terminal(qr)

    # Post-processing
    if qr.evaluation_summary.verdict in ("PASS", "PASS_WITH_WARNINGS"):
        console.print("\n[bold]후처리[/bold]")
        patches = classify_boundaries(output)
        if patches:
            for p in patches:
                console.print(f"  {p['name']:20s} → {p['type']}")
            if click.confirm("  경계 조건을 자동 생성할까요?", default=True):
                write_boundary_conditions(output, patches)
                console.print("  [green]✓[/green] 0/p, U, k, omega, nut 생성 완료")

        if click.confirm("  VTK 파일을 내보낼까요?", default=True):
            vtk_path = export_vtk(output)
            if vtk_path:
                console.print(f"  [green]✓[/green] {vtk_path}")

    console.print(f"\n[bold green]완료![/bold green] Case: {output}")


@cli.command("stats")
@click.argument("case_dir", type=click.Path(exists=True, path_type=Path))
def stats_cmd(case_dir: Path) -> None:
    """beta2279 — Mesh quality stats report (commercial-grade table).

    case_dir/native_bl_quality.json 의 메트릭을 사람-친화적 표로 출력.
    cfMesh checkMesh / Pointwise mesh metrics 동등.

    예시::

        auto-tessell stats ./case
    """
    import json
    qjson = case_dir / "native_bl_quality.json"
    if not qjson.exists():
        console.print(f"[bold red]✗ quality JSON 없음: {qjson}[/bold red]")
        console.print("  BL 가 적용된 case 가 아니거나 BL 실패.")
        sys.exit(1)

    try:
        data = json.loads(qjson.read_text())
    except Exception as exc:
        console.print(f"[bold red]✗ JSON 파싱 실패: {exc}[/bold red]")
        sys.exit(1)

    console.print(f"\n[bold cyan]Mesh Quality Report[/bold cyan] — {case_dir}\n")

    # Topology section
    console.print("[bold]Topology[/bold]")
    console.print(f"  Wall faces       : {data.get('n_wall_faces', 0):>10,}")
    console.print(f"  Wall vertices    : {data.get('n_wall_verts', 0):>10,}")
    console.print(f"  BL prism cells   : {data.get('n_prism_cells', 0):>10,}")
    console.print(f"  New points       : {data.get('n_new_points', 0):>10,}")

    # Geometry section
    console.print("\n[bold]Geometry[/bold]")
    console.print(f"  Total thickness  : {data.get('total_thickness', 0):>10.6e} m")
    console.print(f"  Bbox diagonal    : {data.get('bbox_diag', 0):>10.4f} m")
    console.print(f"  Thickness/bbox   : {data.get('thickness_to_bbox_ratio', 0):>10.4%}")

    # Quality section
    console.print("\n[bold]Quality[/bold]")
    n_deg = data.get("n_degenerate_prisms", 0)
    max_ar = data.get("max_aspect_ratio", 0)
    n_p = max(1, data.get("n_prism_cells", 1))
    color = "red" if n_deg > 0.5 * n_p else "yellow" if n_deg > 0 else "green"
    console.print(f"  Max aspect ratio : {max_ar:>10.1f}")
    console.print(f"  Degenerate prisms: [{color}]{n_deg:>10,} ({100*n_deg/n_p:.1f}%)[/{color}]")

    # Wall preserve section
    wp = data.get("wall_preserve", {})
    within = wp.get("within_envelope", False)
    color = "green" if within else "red"
    console.print("\n[bold]Wall Preservation[/bold] (cfMesh/T-Rex equivalent)")
    console.print(f"  Max diff (abs)   : {wp.get('max_diff', 0):>10.6e}")
    console.print(f"  Max diff (rel)   : {wp.get('max_diff_rel', 0):>10.2e}")
    console.print(f"  Drift count      : {wp.get('n_drift', 0):>10}")
    console.print(f"  Within envelope  : [{color}]{within!s:>10}[/{color}] (eps={wp.get('envelope_eps_rel', 1e-6):.0e})")

    # Force-snap section
    fs = data.get("force_snap", {})
    console.print("\n[bold]Force-snap[/bold]")
    console.print(f"  Snaps applied    : {fs.get('n_applied', 0):>10}")
    console.print(f"  Pre-snap max diff: {fs.get('max_diff', 0):>10.6e}")

    # Config section
    cfg = data.get("config", {})
    console.print("\n[bold]Config[/bold]")
    console.print(f"  num_layers       : {cfg.get('num_layers', '-')}")
    console.print(f"  growth_ratio     : {cfg.get('growth_ratio', '-')}")
    console.print(f"  first_thickness  : {cfg.get('first_thickness', 0):.6e}")
    if cfg.get("target_y_plus"):
        console.print(f"  target_y_plus    : {cfg['target_y_plus']}")
    if cfg.get("flow_fluid_preset"):
        console.print(f"  flow_fluid_preset: {cfg['flow_fluid_preset']}")
    console.print()


@cli.command("convert")
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path))
def convert_cmd(input_path: Path, output_path: Path) -> None:
    """beta2278 — Direct mesh format conversion (meshio-style).

    OpenFOAM polyMesh 단계 없이 input mesh 를 다른 format 으로 직접 변환.
    상용 도구의 "Save As" UX 동등.

    예시::

        auto-tessell convert mesh.stl mesh.obj
        auto-tessell convert input.vtu output.bdf  # VTK → Nastran
        auto-tessell convert geom.step out.stl     # STEP → STL
    """
    import meshio
    from core.analyzer.file_reader import load_mesh
    import numpy as np

    console.print(f"[bold cyan]Convert[/bold cyan] {input_path} → {output_path}")
    try:
        tm = load_mesh(input_path)
        V = np.asarray(tm.vertices)
        F = np.asarray(tm.faces)
        console.print(f"  loaded V={V.shape[0]} F={F.shape[0]}")

        # Determine output format from extension.
        ext = output_path.suffix.lower()
        meshio_ext_map = {
            ".stl": "stl", ".obj": "obj", ".ply": "ply",
            ".vtu": "vtu", ".vtk": "vtk", ".vtp": "vtp",
            ".msh": "gmsh22",  # default Gmsh
            ".bdf": "nastran", ".nas": "nastran",
            ".inp": "abaqus", ".dat": "tecplot",
            ".mesh": "medit", ".xdmf": "xdmf",
        }
        fmt = meshio_ext_map.get(ext)
        if fmt is None:
            console.print(f"[bold red]✗ 지원하지 않는 출력 포맷: {ext}[/bold red]")
            sys.exit(1)

        mesh = meshio.Mesh(
            points=V.astype(np.float64),
            cells=[meshio.CellBlock("triangle", F.astype(np.int64))],
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        meshio.write(str(output_path), mesh, file_format=fmt)
        console.print(f"[bold green]✓[/bold green] {output_path} ({output_path.stat().st_size}b)")
    except Exception as exc:
        console.print(f"[bold red]✗ 변환 실패: {exc}[/bold red]")
        sys.exit(1)


@cli.command("smoketest")
@click.option(
    "--engine",
    type=click.Choice(["tet", "hex", "poly", "all"]),
    default="tet", show_default=True,
)
@click.pass_context
def smoketest(ctx: click.Context, engine: str) -> None:
    """beta2276 — Installation smoke test. 단순 cube → 메쉬 + BL → 검증.

    상용 도구의 "Verify Installation" 동등. 모든 의존성 + native engine + BL +
    quality JSON 동작 확인.
    """
    import tempfile
    import time
    import numpy as np
    import trimesh

    console.print("[bold]Auto-Tessell smoketest[/bold] — verifying installation...")
    overall_t0 = time.perf_counter()
    failures: list[str] = []

    m = trimesh.creation.box(extents=[1, 1, 1])
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    console.print(f"  cube V={V.shape[0]} F={F.shape[0]}")

    engines = ["tet", "hex", "poly"] if engine == "all" else [engine]
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path as _P
        for eng in engines:
            case = _P(td) / f"c_{eng}"
            t0 = time.perf_counter()
            try:
                if eng == "tet":
                    from core.generator.native_tet.mesher import generate_native_tet
                    r = generate_native_tet(
                        V, F, case, seed_density=4,
                        enable_phase_a=True, enable_phase_b=False,
                        enable_phase_c=False,
                    )
                elif eng == "hex":
                    from core.generator.native_hex.mesher import generate_native_hex
                    r = generate_native_hex(V, F, case, seed_density=8)
                else:
                    from core.generator.native_poly.voronoi import (
                        generate_native_poly_voronoi,
                    )
                    r = generate_native_poly_voronoi(V, F, case, seed_density=8)

                gen_t = time.perf_counter() - t0
                if not r.success:
                    failures.append(f"{eng}: gen FAIL")
                    console.print(f"  [red]✗[/red] {eng:5}: gen FAIL")
                    continue
                from core.layers.native_bl import generate_native_bl, BLConfig
                bl = generate_native_bl(
                    case, BLConfig(num_layers=3, first_thickness=0.02),
                    engine_tag=eng,
                )
                bl_t = time.perf_counter() - t0 - gen_t
                wp = bl.wall_preserve_within_envelope
                console.print(
                    f"  [{'green' if wp else 'red'}]"
                    f"{'✓' if wp else '✗'}[/]"
                    f" {eng:5}: cells={r.n_cells} prisms={bl.n_prism_cells} "
                    f"wall_preserve={wp} ({gen_t + bl_t:.1f}s)"
                )
                if not wp:
                    failures.append(f"{eng}: wall_preserve violated")
            except Exception as exc:
                failures.append(f"{eng}: EXC {str(exc)[:80]}")
                console.print(f"  [red]✗[/red] {eng:5}: EXC {str(exc)[:60]}")

    elapsed = time.perf_counter() - overall_t0
    console.print(f"\nElapsed: {elapsed:.1f}s")
    if failures:
        console.print(f"[bold red]FAIL: {len(failures)} error(s)[/bold red]")
        for f in failures:
            console.print(f"  • {f}")
        ctx.exit(1)
    console.print("[bold green]✓ All checks passed[/bold green]")


if __name__ == "__main__":
    cli()
