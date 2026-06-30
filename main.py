from __future__ import annotations

from config import build_source_definitions, load_config
from firefly import _build_firefly_transaction
from imap_client import mark_message_processed as _mark_message_processed
from parser import convert_to_timezone, extract_transaction_details
from service import TransactionImportService



def main():
    config = load_config()
    service = TransactionImportService.from_config(config)
    service.run()


if __name__ == "__main__":
    main()
