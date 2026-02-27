"""DB 自動更新: cron から定期実行し、ABC126 以降の新着問題を ChromaDB に差分反映する。"""
import time
from datetime import datetime, timezone
from pathlib import Path

from src import load_config
from src.atcoder_metadata import get_target_abc_problems
from src.config import (
    DEFAULT_DB_PATH,
    DEFAULT_LOG_DIR,
    DEFAULT_UPDATE_REPORT_FILENAME,
)
from src.embedding_db import (
    COLLECTION_NAME,
    GeminiChromaEmbeddingFunction,
    build_combined_text,
    get_chroma_client,
    get_existing_ids,
    upsert_problems,
)
from src.llm_extract import extract_keywords_and_summary
from src.logging_report import (
    console_error,
    console_info,
    get_logger,
    setup_logging,
    write_report_row,
)
from src.scrape import scrape_one_problem


def _write_summary_row(
    report_path: str,
    processed_count: int,
    upserted_count: int | None = None,
) -> None:
    """実行サマリ行を追記する（死活監視用 Heartbeat）。"""
    row = {
        "type": "summary",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "processed_count": processed_count,
    }
    if upserted_count is not None:
        row["upserted_count"] = upserted_count
    write_report_row(row, report_path)


def run(
    db_path: str = DEFAULT_DB_PATH,
    log_dir: str = DEFAULT_LOG_DIR,
) -> None:
    """自動更新パイプライン本体。差分がある問題のみスクレイプ・LLM 抽出・Upsert する。"""
    load_config()
    setup_logging(log_dir)
    logger = get_logger("auto_update")
    report_path = str(Path(log_dir) / DEFAULT_UPDATE_REPORT_FILENAME)

    try:
        client = get_chroma_client(db_path)
        emb_fn = GeminiChromaEmbeddingFunction()
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=emb_fn,
        )
        existing_ids = get_existing_ids(collection)
    except Exception as e:
        logger.exception("ChromaDB 接続失敗")
        console_error(f"[ERROR] ChromaDB: {e!s}")
        _write_summary_row(report_path, 0)
        raise

    try:
        target_list = get_target_abc_problems(min_contest_number=126)
    except Exception as e:
        logger.exception("AtCoder Problems API 取得失敗")
        console_error(f"[ERROR] API: {e!s}")
        _write_summary_row(report_path, 0)
        raise

    diff_metas = [p for p in target_list if p["id"] not in existing_ids]
    # get_target_abc_problems がコンテスト番号・問題インデックス昇順でソート済みのためそのまま利用

    if not diff_metas:
        console_info("差分なし。終了します。")
        _write_summary_row(report_path, 0)
        return

    console_info(f"差分 {len(diff_metas)} 問を処理します。")
    report_rows: list[dict] = []
    to_upsert: list[dict] = []

    for i, meta in enumerate(diff_metas, 1):
        pid = meta["id"]
        row: dict = {
            "problem_id": pid,
            "contest_id": meta["contest_id"],
            "scrape_status": "OK",
            "llm_status": "OK",
            "db_upsert_status": "NG",
            "error_message": "",
        }
        console_info(f"[{i}/{len(diff_metas)}] {pid}")

        try:
            problem_statement, editorial_text = scrape_one_problem(meta)
        except Exception as e:
            row["scrape_status"] = "NG"
            row["error_message"] = (row.get("error_message") or "") + f" Scrape: {e!s}"
            logger.exception("Scraping failed for %s", pid)
            console_error(f"[ERROR] {pid}: Failed at Scraping ({e!s})")
            report_rows.append(row)
            continue

        time.sleep(1)  # Gemini API 制限対策（run_batch と同様）
        try:
            gemini_extract = extract_keywords_and_summary(
                problem_statement,
                editorial_text,
            )
        except Exception as e:
            row["llm_status"] = "NG"
            row["error_message"] = (row.get("error_message") or "") + f" LLM: {e!s}"
            logger.exception("LLM extract failed for %s", pid)
            console_error(f"[ERROR] {pid}: Failed at LLM ({e!s})")
            report_rows.append(row)
            continue

        if not gemini_extract:
            row["llm_status"] = "NG"
            row["error_message"] = (row.get("error_message") or "") + " LLM returned None."
            console_error(f"[ERROR] {pid}: LLM returned None")
            report_rows.append(row)
            continue

        item = {
            "id": pid,
            "title": meta["title"],
            "url": meta["url"],
            "difficulty": meta.get("difficulty"),
            "gemini_extract": gemini_extract,
        }
        to_upsert.append(item)
        report_rows.append(row)

    upserted_ids: set[str] = set()
    if to_upsert:
        try:
            ids = [x["id"] for x in to_upsert]
            documents = [build_combined_text(x) for x in to_upsert]
            metadatas = [
                {"title": x["title"], "url": x["url"], "difficulty": x.get("difficulty")}
                for x in to_upsert
            ]
            upsert_problems(collection, ids, documents, metadatas)
            upserted_ids = set(ids)
            console_info(f"完了: {len(ids)} 件を ChromaDB に保存しました。（パス: {db_path}）")
        except Exception as e:
            logger.exception("DB upsert failed")
            console_error(f"[ERROR] DB upsert failed: {e!s}")
    else:
        console_info("DB 投入対象が 0 件です。")

    for r in report_rows:
        r["db_upsert_status"] = "OK" if r["problem_id"] in upserted_ids else "NG"

    for r in report_rows:
        write_report_row(r, report_path)

    _write_summary_row(report_path, len(diff_metas), upserted_count=len(upserted_ids))
    console_info(f"レポート: {report_path}")


def main() -> None:
    """CLI 入口。引数なしでデフォルト設定で実行する。"""
    run()


if __name__ == "__main__":
    main()
