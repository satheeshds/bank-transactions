from pathlib import Path
import tomllib

from imap_tools import AND, MailBox


CONFIG_PATH = Path(__file__).with_name("config.toml")


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)


def main():
    config = load_config()
    mailbox_config = config["mailbox"]
    fetch_config = config.get("fetch", {})
    query = AND(**config["query"])

    print("Hello from bank-transactions!")
    with MailBox(mailbox_config["host"]).login(
        mailbox_config["username"],
        mailbox_config["password"],
    ) as mailbox:
        for msg in mailbox.fetch(
            query,
            reverse=fetch_config.get("reverse", True),
            limit=fetch_config.get("limit", 15),
        ):
            print(msg.date, msg.subject, len(msg.text or msg.html))


if __name__ == "__main__":
    main()
