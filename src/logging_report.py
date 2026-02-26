"""堅牢なロギング・レポート。Non-blocking: ログ/レポート/コンソール出力は try-except でガードする。"""
import json
import logging
import sys
from pathlib import Path

APP_LOG_FILENAME = "app.log"


def setup_logging(log_dir: str) -> None:
    """logs/ を作成し、logging を設定。app.log にファイル出力。例外時もメイン処理を止めない。"""
    try:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        log_file = path / APP_LOG_FILENAME

        root = logging.getLogger("atcoder_rag")
        root.setLevel(logging.DEBUG)
        if root.handlers:
            return

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        # Non-blocking: ログ設定に失敗しても何もしない（または stderr に短く出す）
        try:
            print(" [WARN] Logging setup failed.", file=sys.stderr)
        except Exception:
            pass


def get_logger(name: str) -> logging.Logger:
    """設定済みのルートロガーを名前付きで返す。"""
    return logging.getLogger("atcoder_rag").getChild(name)


def write_report_row(row: dict, report_path: str) -> None:
    """レポートに 1 行（1 JSON オブジェクト）を追記。try-except でガード。"""
    try:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        try:
            print(" [WARN] Report write failed.", file=sys.stderr)
        except Exception:
            pass


def write_report_rows(rows: list[dict], report_path: str) -> None:
    """レポートを一括書き出し（実行終了時のまとめ用）。try-except でガード。"""
    try:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        try:
            print(" [WARN] Report write failed.", file=sys.stderr)
        except Exception:
            pass


def console_info(msg: str) -> None:
    """標準出力に進捗メッセージを出す。try-except でガード。"""
    try:
        print(msg, flush=True)
    except Exception:
        pass


def console_error(msg: str) -> None:
    """標準エラーにエラーメッセージを出す。try-except でガード。"""
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:
        pass
