"""Command-line interface (CLI) for shop-support-agent."""

from __future__ import annotations

import asyncio
from datetime import datetime
import sys
import click

from shopagent.core.clock import get_clock
from shopagent.core.logging import setup_logging
from shopagent.domain.seeder import generate_seed_data
from shopagent.domain.verifier import verify_dataset
from shopagent.infra.db.session import async_engine, async_session_factory
from shopagent.infra.db.tables import Base


@click.group()
def cli() -> None:
    """Shop Support Agent Management CLI."""
    pass


@cli.command("init-db")
def init_db_cmd() -> None:
    """Initialize database tables."""
    async def _init() -> None:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        click.echo("Khởi tạo cấu trúc bảng cơ sở dữ liệu thành công.")

    asyncio.run(_init())


@cli.command("seed")
@click.option("--seed", default=20261111, type=int, help="Random seed for deterministic generation.")
@click.option("--now", default="2026-11-11T09:00:00+07:00", type=str, help="Reference ISO timestamp.")
@click.option("--customers", default=300, type=int, help="Number of customers.")
@click.option("--products", default=120, type=int, help="Number of products.")
@click.option("--orders", default=1500, type=int, help="Number of orders.")
def seed_cmd(seed: int, now: str, customers: int, products: int, orders: int) -> None:
    """Seed database with realistic deterministic data."""
    async def _run() -> None:
        try:
            now_dt = datetime.fromisoformat(now)
        except Exception:
            now_dt = datetime(2026, 11, 11, 9, 0, 0)

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        async with async_session_factory() as session:
            click.echo(f"Đang sinh dữ liệu mẫu với seed={seed}, mốc thời gian={now_dt.isoformat()}...")
            counts = await generate_seed_data(
                session=session,
                seed=seed,
                now=now_dt,
                num_customers=customers,
                num_products=products,
                num_orders=orders,
            )
            click.echo(
                f"Đã sinh xong: {counts['staff']} nhân viên, {counts['customers']} khách hàng, "
                f"{counts['products']} sản phẩm, {counts['variants']} phân loại, "
                f"{counts['orders']} đơn hàng, {counts['returns']} yêu cầu trả hàng."
            )

    asyncio.run(_run())


@cli.command("verify-data")
def verify_data_cmd() -> None:
    """Verify data invariants and accounting integrity."""
    async def _run() -> None:
        async with async_session_factory() as session:
            click.echo("Đang kiểm tra tính toàn vẹn dữ liệu và 6 bất biến nghiệp vụ...")
            result = await verify_dataset(session)

            click.echo(f"Tổng kiểm tra: {result.checks_run} | Đạt: {result.passed} | Không đạt: {result.failed}")
            if not result.is_valid:
                click.echo("CÁC LỖI VI PHẠM PHÁT HIỆN ĐƯỢC:")
                for err in result.errors:
                    click.echo(f"- {err}")
                sys.exit(1)
            else:
                click.echo("Toàn bộ kiểm tra dữ liệu và bất biến ĐẠT 100%.")

    asyncio.run(_run())


@cli.group("eval")
def eval_group() -> None:
    """Evaluation harness commands."""
    pass


@eval_group.command("run")
@click.option("--agent", default="oracle", type=str, help="Agent to evaluate: oracle, null, main.")
@click.option("--group", default="all", type=str, help="Scenario group: A, B, C, D, E, F, G, H, I, V, or all.")
@click.option("--mode", default="offline", type=str, help="Evaluation mode: offline or online.")
def eval_run_cmd(agent: str, group: str, mode: str) -> None:
    """Run evaluation scenarios."""
    click.echo(f"Chạy đánh giá kịch bản: agent={agent}, group={group}, mode={mode}")
    # Handled in Phase 2
    from evals.harness.runner import run_eval_cli
    asyncio.run(run_eval_cli(agent=agent, group=group, mode=mode))


if __name__ == "__main__":
    cli()
