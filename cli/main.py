from __future__ import annotations

from app.config import build_source_definitions, load_config
from app.services.firefly_builder import _build_firefly_transaction
from app.services.imap import mark_message_processed as _mark_message_processed
from app.services.parser import convert_to_timezone, extract_transaction_details
from app.services.service import TransactionImportService



def main():
    config = load_config()
    service = TransactionImportService.from_config(config)
    service.run()


if __name__ == "__main__":
    main()
