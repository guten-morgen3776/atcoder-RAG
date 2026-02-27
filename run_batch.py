"""メインのバッチ処理: コンテスト・問題範囲を指定して一括でDB化する。"""
import argparse
import json
import time
from pathlib import Path

from src import load_config
from src.atcoder_metadata import list_problems_in_range
from src.config import (
    DEFAULT_DB_PATH,
    DEFAULT_LOG_DIR,
    DEFAULT_RAW_DATA_DIR,
    DEFAULT_REPORT_FILENAME,
)
from src.embedding_db import (
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
    write_report_rows,
)
from src.models import IntermediateProblem
from src.scrape import scrape_one_problem

COLLECTION_NAME = "atcoder_problems"


def _raw_dir(raw_data_dir: str) -> Path:
    path = Path(raw_data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_intermediate(problem_id: str, raw_data_dir: str) -> IntermediateProblem | None:
    """data/raw/{problem_id}.json を読み込む。なければ None。"""
    p = _raw_dir(raw_data_dir) / f"{problem_id}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_intermediate(
    problem_id: str,
    data: IntermediateProblem,
    raw_data_dir: str,
) -> None:
    """data/raw/{problem_id}.json に書き出す。"""
    p = _raw_dir(raw_data_dir) / f"{problem_id}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run(
    prefix: str,
    start_num: int,
    end_num: int,
    start_index: str,
    end_index: str,
    db_path: str = DEFAULT_DB_PATH,
    raw_data_dir: str = DEFAULT_RAW_DATA_DIR,
    log_dir: str = DEFAULT_LOG_DIR,
    skip_existing: bool = True,
    force_re_scrape: bool = False,
) -> None:
    """パイプライン本体。複数コンテストを prefix + 番号範囲で一括処理する。"""
    load_config()
    setup_logging(log_dir)
    logger = get_logger("run_batch")
    report_path = str(Path(log_dir) / DEFAULT_REPORT_FILENAME)
    report_rows: list[dict] = []
    all_processed_metas: list[dict] = []

    client = get_chroma_client(db_path)
    emb_fn = GeminiChromaEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=emb_fn,
    )
    existing_ids = get_existing_ids(collection) if skip_existing else set()

    contest_ids = [f"{prefix}{n}" for n in range(start_num, end_num + 1)]
    console_info(
        f"対象: {prefix}{start_num}〜{prefix}{end_num} ({len(contest_ids)} コンテスト), "
        f"問題 {start_index}〜{end_index}"
    )

    for contest_id in contest_ids:
        problems = list_problems_in_range(contest_id, start_index, end_index)
        if not problems:
            console_info(f"[{contest_id}] 該当問題なし、スキップ")
            continue

        to_process = [p for p in problems if p["id"] not in existing_ids]
        if skip_existing and len(to_process) < len(problems):
            console_info(
                f"[{contest_id}] ChromaDB に既存のためスキップ: "
                f"{len(problems) - len(to_process)} 問"
            )
        if not to_process:
            continue

        console_info(f"[{contest_id}] {start_index}〜{end_index} → {len(to_process)} 問を処理")

        for i, meta in enumerate(to_process, 1):
            pid = meta["id"]
            row: dict = {
                "problem_id": pid,
                "contest_id": contest_id,
                "scrape_status": "OK",
                "llm_status": "OK",
                "db_upsert_status": "NG",
                "error_message": "",
            }
            console_info(f"[{contest_id}] [{i}/{len(to_process)}] {pid}")

            intermediate = load_intermediate(pid, raw_data_dir)
            if intermediate is None:
                intermediate = {
                    "id": pid,
                    "title": meta["title"],
                    "url": meta["url"],
                    "difficulty": meta["difficulty"],
                }

            if force_re_scrape or not intermediate.get("problem_statement_ja"):
                try:
                    problem_statement, editorial_text = scrape_one_problem(meta)
                    intermediate["problem_statement_ja"] = problem_statement
                    intermediate["has_official_editorial"] = editorial_text is not None
                    intermediate["editorial_text"] = editorial_text
                    save_intermediate(pid, intermediate, raw_data_dir)
                    console_info(f"[INFO] {pid}: Scraping Success")
                except Exception as e:
                    row["scrape_status"] = "NG"
                    row["error_message"] = (row.get("error_message") or "") + f" Scrape: {e!s}"
                    logger.exception("Scraping failed for %s", pid)
                    console_error(f"[ERROR] {pid}: Failed at Scraping ({e!s})")

            if force_re_scrape or not intermediate.get("gemini_extract"):
                time.sleep(1)  # Gemini API RPM 制限回避。スクレイプの有無に関わらず LLM 呼び出し直前に必ず待機（中間JSON からのリカバリー時も 4 秒間隔を保証）
                try:
                    gemini_extract = extract_keywords_and_summary(
                    intermediate.get("problem_statement_ja", ""),
                    intermediate.get("editorial_text"),
                )
                    intermediate["gemini_extract"] = gemini_extract
                    save_intermediate(pid, intermediate, raw_data_dir)
                    if gemini_extract:
                        console_info(f"[INFO] {pid}: LLM Success")
                    else:
                        row["llm_status"] = "NG"
                        row["error_message"] = (row.get("error_message") or "") + " LLM returned None."
                        console_error(f"[ERROR] {pid}: LLM returned None")
                except Exception as e:
                    row["llm_status"] = "NG"
                    row["error_message"] = (row.get("error_message") or "") + f" LLM: {e!s}"
                    logger.exception("LLM extract failed for %s", pid)
                    console_error(f"[ERROR] {pid}: Failed at LLM ({e!s})")

            report_rows.append(row)
            all_processed_metas.append(meta)

    to_upsert = []
    for meta in all_processed_metas:
        data = load_intermediate(meta["id"], raw_data_dir)
        if data and data.get("gemini_extract"):
            to_upsert.append(data)

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
    write_report_rows(report_rows, report_path)
    console_info(f"レポート: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AtCoder 過去問を指定範囲で一括DB化（RAG用ベクトルDB）",
    )
    parser.add_argument(
        "--prefix",
        required=True,
        help="コンテストIDのプレフィックス（例: abc）",
    )
    parser.add_argument(
        "--start-num",
        type=int,
        required=True,
        help="コンテスト番号の開始（例: 350 → abc350 から）",
    )
    parser.add_argument(
        "--end-num",
        type=int,
        required=True,
        help="コンテスト番号の終了（例: 400 → abc400 まで）",
    )
    parser.add_argument(
        "--start",
        default="C",
        help="開始問題インデックス（例: C）",
    )
    parser.add_argument(
        "--end",
        default="F",
        help="終了問題インデックス（例: F）",
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"ChromaDB 保存先（デフォルト: {DEFAULT_DB_PATH}）",
    )
    parser.add_argument(
        "--raw-dir",
        default=DEFAULT_RAW_DATA_DIR,
        help=f"中間JSON 保存ディレクトリ（デフォルト: {DEFAULT_RAW_DATA_DIR}）",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="ChromaDB に既に存在する問題も再取得・再投入する",
    )
    parser.add_argument(
        "--force-re-scrape",
        action="store_true",
        help="中間JSON があってもスクレイピングからやり直す",
    )
    parser.add_argument(
        "--log-dir",
        default=DEFAULT_LOG_DIR,
        help=f"ログ・レポート出力先（デフォルト: {DEFAULT_LOG_DIR}）",
    )
    args = parser.parse_args()

    if args.start_num > args.end_num:
        raise SystemExit("--start-num は --end-num 以下にしてください。")

    run(
        prefix=args.prefix,
        start_num=args.start_num,
        end_num=args.end_num,
        start_index=args.start,
        end_index=args.end,
        db_path=args.db_path,
        raw_data_dir=args.raw_dir,
        log_dir=args.log_dir,
        skip_existing=not args.no_skip_existing,
        force_re_scrape=args.force_re_scrape,
    )


if __name__ == "__main__":
    main()
