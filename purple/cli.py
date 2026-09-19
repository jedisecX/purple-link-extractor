from __future__ import annotations

from pathlib import Path

import click

from purple.config import load_config
from purple.exporter import export_all, export_domain, export_domain_directory
from purple.importer import Importer
from purple.logconf import setup_logging
from purple.statistics import (
    db_overview,
    domain_links,
    list_domains,
    print_import_stats,
    search_links,
)


@click.group()
@click.option("--config", "config_path", default=None, help="Path to purple.yaml")
@click.option("--db", "db_override", default=None, help="SQLite database path")
@click.pass_context
def main(ctx: click.Context, config_path: str | None, db_override: str | None) -> None:
    overrides = {}
    if db_override:
        overrides["database"] = db_override
    cfg = load_config(config_path, overrides or None)
    setup_logging(cfg.logging.level)
    ctx.ensure_object(dict)
    ctx.obj["cfg"] = cfg


@main.command("import")
@click.argument("target", type=click.Path(exists=True))
@click.option("--recursive", is_flag=True, default=None)
@click.option("--batch-size", type=int, default=None)
@click.pass_context
def import_cmd(ctx, target, recursive, batch_size):
    cfg = ctx.obj["cfg"]
    rec = cfg.import_cfg.recursive if recursive is None else recursive
    batch = cfg.import_cfg.batch_size if batch_size is None else batch_size
    importer = Importer(cfg.database, batch_size=batch, accepted_schemes=cfg.import_cfg.accepted_schemes)
    stats = importer.import_path(Path(target), recursive=rec)
    print_import_stats(stats, Path(cfg.database))


@main.command("stats")
@click.pass_context
def stats_cmd(ctx):
    cfg = ctx.obj["cfg"]
    info = db_overview(cfg.database)
    print("PURPLE LINK EXTRACTOR")
    print("=====================")
    print(f"Links:    {info['links']:,}")
    print(f"Domains:  {info['domains']:,}")
    print(f"Sources:  {info['sources']:,}")
    print()
    for scheme, n in info["schemes"]:
        print(f"{scheme or '?'}: {n:,}")
    print()
    print(f"{'DOMAIN':<40} {'LINKS':>12}")
    print("-" * 54)
    for host, n in info["top_domains"]:
        print(f"{host:<40} {n:>12,}")


@main.command("domains")
@click.option("--limit", default=100, type=int)
@click.option("--offset", default=0, type=int)
@click.pass_context
def domains_cmd(ctx, limit, offset):
    cfg = ctx.obj["cfg"]
    rows = list_domains(cfg.database, limit=limit, offset=offset)
    print(f"{'DOMAIN':<40} {'LINKS':>12}")
    print("-" * 54)
    for r in rows:
        print(f"{r['hostname']:<40} {r['link_count']:>12,}")


@main.command("domain")
@click.argument("hostname")
@click.option("--limit", default=100, type=int)
@click.option("--offset", default=0, type=int)
@click.pass_context
def domain_cmd(ctx, hostname, limit, offset):
    cfg = ctx.obj["cfg"]
    info, links = domain_links(cfg.database, hostname, limit=limit, offset=offset)
    if not info:
        raise click.ClickException(f"No domain matching {hostname}")
    total = sum(r["link_count"] for r in info)
    print(f"Domain: {hostname}")
    print(f"Links: {total:,}")
    print()
    for url in links:
        print(url)


@main.command("search")
@click.argument("query")
@click.option("--limit", default=100, type=int)
@click.pass_context
def search_cmd(ctx, query, limit):
    cfg = ctx.obj["cfg"]
    rows = search_links(cfg.database, query, limit=limit)
    for r in rows:
        print(r["normalized_url"])


@main.command("export")
@click.argument("fmt", type=click.Choice(["csv", "json", "dir"]))
@click.option("--out", default=None)
@click.pass_context
def export_cmd(ctx, fmt, out):
    cfg = ctx.obj["cfg"]
    if fmt == "dir":
        dest = Path(out or cfg.output.directory)
        export_domain_directory(cfg.database, dest)
        print(dest)
        return
    dest = Path(out or (f"purple-export.{fmt}"))
    export_all(cfg.database, dest, fmt=fmt)
    print(dest)


@main.command("export-domain")
@click.argument("hostname")
@click.option("--format", "fmt", default="txt", type=click.Choice(["txt", "csv", "json"]))
@click.option("--out", default=None)
@click.pass_context
def export_domain_cmd(ctx, hostname, fmt, out):
    cfg = ctx.obj["cfg"]
    dest = Path(out or f"{hostname}.{fmt}")
    export_domain(cfg.database, hostname, dest, fmt=fmt)
    print(dest)


@main.command("harvest")
@click.argument("dork")
@click.option("--engine", "engines", multiple=True, type=click.Choice(["yahoo", "bing"]), default=("yahoo", "bing"))
@click.option("--pages", default=5, type=int, help="Result pages per engine (max 20)")
@click.option("--delay", default=2.0, type=float, help="Seconds between search pages")
@click.pass_context
def harvest_cmd(ctx, dork, engines, pages, delay):
    """Dork Yahoo/Bing, unwrap result links, index into the existing DB.

    Does not download documents. Does not write csv/txt — use `purple export`.
    """
    from purple.database import get_db
    from purple.harvester import SearchHarvester
    from purple.services import library as lib

    cfg = ctx.obj["cfg"]
    harvester = SearchHarvester(delay=delay)
    found = harvester.harvest(dork, engines=list(engines) or ["yahoo", "bing"], pages=pages)
    click.echo(f"Discovered {found.discovered} URLs across {found.pages_fetched} pages")
    importer = Importer(cfg.database, accepted_schemes=cfg.import_cfg.accepted_schemes)
    label = f"harvest:{'+'.join(found.engines)}:{dork}"
    stats = importer.ingest_urls(found.urls, source_name=label[:240], label="harvest")
    with get_db(cfg.database) as conn:
        lib.log_activity(conn, "HARVEST INDEXED", f"{dork} +{stats.unique_urls}")
        conn.commit()
    print_import_stats(stats, Path(cfg.database))


@main.command("serve")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8747, type=int)
@click.pass_context
def serve_cmd(ctx, host, port):
    """Launch the Purple Control Center."""
    import uvicorn
    from purple.api.app import create_app

    cfg = ctx.obj["cfg"]
    app = create_app(cfg.database)
    click.echo(f"Purple Control Center  http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
